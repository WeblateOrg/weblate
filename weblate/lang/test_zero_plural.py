# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Regression tests for shared zero-plural creation and upgrades."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from runpy import run_path
from threading import Barrier
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.test.utils import override_settings

from weblate.formats.ttkit import StringsdictFormat
from weblate.lang.models import Language, Plural
from weblate.trans.tests.utils import get_test_file


class ZeroPluralTest(TransactionTestCase):
    def test_concurrent_format_creation(self) -> None:
        language = Language.objects.create(code="qaa", name="Zero plural test")
        Plural.objects.create(
            language=language,
            source=Plural.SOURCE_CLDR,
            number=2,
            formula="n != 1",
        )
        barrier = Barrier(2, timeout=10)
        original_save = Plural.save

        def save_plural(plural: Plural, *args: object, **kwargs: object) -> None:
            if plural.pk is None and plural.source == Plural.SOURCE_CLDR_ZERO:
                barrier.wait()
            original_save(plural, *args, **kwargs)

        def create_plural() -> int:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout = '15s'")
                storage = StringsdictFormat(get_test_file("cs.stringsdict"))
                return storage.get_plural(Language.objects.get(pk=language.pk)).pk
            finally:
                connections.close_all()

        with patch.object(Plural, "save", save_plural), ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(create_plural) for _ in range(2)]
            ids = [future.result(timeout=20) for future in futures]

        self.assertEqual(ids[0], ids[1])
        self.assertEqual(
            language.plural_set.filter(source=Plural.SOURCE_CLDR_ZERO).count(), 1
        )

    def test_constraint_only_limits_zero_plurals(self) -> None:
        language = Language.objects.create(code="qaa", name="Zero plural test")
        for _ in range(2):
            Plural.objects.create(language=language, source=Plural.SOURCE_MANUAL)
        Plural.objects.create(language=language, source=Plural.SOURCE_CLDR_ZERO)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Plural.objects.create(language=language, source=Plural.SOURCE_CLDR_ZERO)

    def test_populated_upgrade(self) -> None:
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old = [
            ("lang", "0007_alter_language_code"),
            ("trans", "0121_clear_github_app_push"),
        ]
        scripts = Path(__file__).resolve().parents[2] / "ci" / "migrate-scripts"
        try:
            executor.migrate(old)
            historical_apps = executor.loader.project_state(old).apps
            with patch("django.apps.apps", historical_apps):
                run_path(str(scripts / "setup-zero-plurals.py"))
            historical_plural = historical_apps.get_model("lang", "Plural")
            oldest_id = historical_plural.objects.get(
                language__code="qaa_ZERO", source=3, number=3
            ).pk
            singleton_id = historical_plural.objects.get(
                language__code="qab_ZERO", source=3
            ).pk
            MigrationExecutor(connection).migrate(latest)
            zero = Plural.objects.get(language__code="qaa_ZERO", source=3)
            self.assertEqual(zero.pk, oldest_id)
            self.assertEqual(zero.formula, "n == 0 ? 0 : 1")
            # MigrationExecutor omits the signals run by the real upgrade command.
            with override_settings(UPDATE_LANGUAGES=True):
                call_command("migrate", interactive=False, verbosity=0)
            run_path(str(scripts / "assert-zero-plurals.py"))
            self.assertEqual(
                Plural.objects.get(language__code="qaa_ZERO", source=3).pk, oldest_id
            )
            self.assertEqual(
                Plural.objects.get(language__code="qab_ZERO", source=3).pk, singleton_id
            )
        finally:
            MigrationExecutor(connection).migrate(latest)
