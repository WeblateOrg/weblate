# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.db import DatabaseError, connection
from django.test import TestCase, TransactionTestCase

from weblate.auth.models import User
from weblate.lang.models import Plural
from weblate.trans.models import Unit
from weblate.utils.search_benchmark import (
    CASES,
    VARIANTS,
    Case,
    Profile,
    correctness,
    explain,
    matching_units,
    operation_sql,
    seed_fixture,
    set_source_scenario,
    write_summary,
)


class SearchBenchmarkSequenceTest(TestCase):
    def test_stale_plural_sequence(self) -> None:
        plural = Plural.objects.filter(language__code__in=("en", "pl", "cs")).latest(
            "pk"
        )
        self.assertGreater(plural.pk, 1)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('lang_plural', 'id')::regclass, %s)",
                [plural.pk - 1],
            )

        seed_fixture(Profile(1, 1), rebuild_indexes=False)
        self.assertTrue(Plural.objects.filter(pk=plural.pk).exists())


class SearchBenchmarkTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_fixture(Profile(80, 8), rebuild_indexes=False)

    def test_variants_match_production(self) -> None:
        with TemporaryDirectory() as directory:
            for scenario in ("no-parents", "mixed"):
                set_source_scenario(scenario)
                for case in CASES:
                    with self.subTest(scenario=scenario, case=case.name):
                        user = User.objects.get(
                            username="benchmark-superuser"
                            if case.superuser
                            else "benchmark-restricted"
                        )
                        correctness(user, case, Path(directory))

    def test_custom_source_and_missing_canonical_source(self) -> None:
        user = User.objects.get(username="benchmark-superuser")
        child = Unit.objects.get(
            translation__component__slug="benchmark-0",
            translation__language_code="pl",
            id_hash=2,
        )
        parent = Unit.objects.get(
            translation__component__slug="benchmark-0",
            translation__language_code="cs",
            id_hash=2,
        )
        Unit.objects.filter(pk=child.pk).update(source="canonicalonly")
        Unit.objects.filter(pk=parent.pk).update(target="parentonly")
        for scenario, term, expected in (
            ("no-parents", "canonicalonly", True),
            ("mixed", "canonicalonly", False),
            ("mixed", "parentonly", True),
        ):
            set_source_scenario(scenario)
            for language_shape, source_shape in VARIANTS:
                with self.subTest(
                    scenario=scenario, term=term, variant=(language_shape, source_shape)
                ):
                    self.assertEqual(
                        matching_units(user, "pl", term, language_shape, source_shape)
                        .filter(pk=child.pk)
                        .exists(),
                        expected,
                    )
        set_source_scenario("no-parents")
        Unit.objects.filter(pk=child.pk).update(
            details={"translation_parent": {"missing": True}}
        )
        for language_shape, source_shape in VARIANTS:
            self.assertFalse(
                matching_units(
                    user, "pl", "canonicalonly", language_shape, source_shape
                )
                .filter(pk=child.pk)
                .exists()
            )

    def test_language_case_and_unknown_code(self) -> None:
        user = User.objects.get(username="benchmark-superuser")
        with TemporaryDirectory() as directory:
            for language in ("pl", "PL", "not-a-language"):
                for case in (
                    Case("language", language, "rareword", True),
                    Case("language", language, "rareword", True, ":="),
                ):
                    correctness(user, case, Path(directory))

    def test_fixture_exercises_access_restrictions(self) -> None:
        user = User.objects.get(username="benchmark-restricted")
        visible = Unit.objects.filter_access(user)
        self.assertEqual(
            set(
                visible.values_list("translation__component__project__slug", flat=True)
            ),
            {"benchmark-public", "benchmark-protected", "benchmark-granted"},
        )
        self.assertTrue(
            visible.filter(translation__component__slug="benchmark-0").exists()
        )
        self.assertFalse(
            visible.filter(translation__component__slug="benchmark-65").exists()
        )

    def test_operation_values(self) -> None:
        user = User.objects.get(username="benchmark-superuser")
        units = matching_units(user, "pl", "rareword", "ids", "id-union")
        # The test transaction already contains writes, so inspect plans
        # without changing its transaction mode to READ ONLY.
        with connection.cursor() as cursor:
            for operation in ("count", "sum", "page"):
                sql, params = operation_sql(units, operation)
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                if operation == "count":
                    self.assertEqual(rows[0][0], units.count())
                elif operation == "sum":
                    words = list(units.values_list("num_words", flat=True))
                    self.assertEqual(rows[0][0], sum(words) if words else None)
                else:
                    self.assertEqual(
                        [row[0] for row in rows],
                        list(
                            units.order_by("-priority", "position", "pk").values_list(
                                "pk", flat=True
                            )[:22]
                        ),
                    )

    def test_summary_skips_unused_sum_and_preserves_timeouts(self) -> None:
        records: list[dict] = []
        for scenario, count_words, page_used, failed_operation in (
            ("True", True, True, "sum"),
            ("False", False, True, "sum"),
            ("empty", True, False, "page"),
        ):
            records.extend(
                {
                    "scenario": scenario,
                    "case": "summary",
                    "variant": "join-join",
                    "operation": operation,
                    "repetition": 1,
                    "warmup": False,
                    "word_summary_used": count_words,
                    "page_used": page_used,
                    "build_and_lookup_ms": 2,
                    "execution_ms": 10,
                    "planning_ms": 1,
                    "total_ms": 13,
                    **({"error": "timeout"} if operation == failed_operation else {}),
                }
                for operation in ("count", "sum", "page")
            )
        with TemporaryDirectory() as directory:
            write_summary(records, Path(directory))
            summary = (Path(directory) / "summary.md").read_text()
        self.assertIn(
            "| False | summary | join-join | 24.00 | 24.00–24.00 | 0 |", summary
        )
        self.assertIn("| True | summary | join-join | — | — | 1 |", summary)
        self.assertIn(
            "| empty | summary | join-join | 24.00 | 24.00–24.00 | 0 |", summary
        )


class SearchBenchmarkExecutionTest(TransactionTestCase):
    def test_timeout_rolls_back_only_measurement(self) -> None:
        with self.assertRaises(DatabaseError):
            explain("SELECT pg_sleep(2)", (), 1)
        self.assertIn("Plan", explain("SELECT 1", (), 1))

    def test_measurements_cannot_write(self) -> None:
        with self.assertRaises(DatabaseError):
            explain("DELETE FROM trans_unit WHERE false", (), 1)
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            self.assertEqual(cursor.fetchone()[0], "off")
