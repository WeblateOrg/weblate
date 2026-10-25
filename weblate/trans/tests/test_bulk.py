# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from time import monotonic, sleep
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import SimpleTestCase, TransactionTestCase

from weblate.lang.models import Language
from weblate.trans.bulk import BulkReplacement, bulk_perform
from weblate.trans.models import Component, Unit
from weblate.trans.tests.utils import RepoTestMixin, clear_users_cache, get_test_actor


class BulkReplacementTest(SimpleTestCase):
    def test_literal_whitespace_and_escapes(self) -> None:
        replacement = BulkReplacement(" value ", r" \g<1> ")
        self.assertEqual(replacement.replace("A value B"), r"A \g<1> B")

    def test_captures(self) -> None:
        replacement = BulkReplacement(
            r"(?P<first>\w+) (\w+)", r"\g<2> \g<first> ", "regex"
        )
        self.assertEqual(replacement.replace("hello world"), "world hello ")

    def test_zero_width_and_empty_replacement(self) -> None:
        self.assertEqual(
            BulkReplacement("^", "prefix ", "regex").replace("value"), "prefix value"
        )
        self.assertEqual(BulkReplacement("value", "", "regex").replace("value"), "")

    def test_optional_capture(self) -> None:
        replacement = BulkReplacement(r"a(b)?", r"\g<1>", "regex")
        self.assertEqual(replacement.replace("a"), "")

    def test_invalid_templates_without_matching_input(self) -> None:
        for template in (r"\g<missing>", r"\g<2>", r"\k"):
            with self.subTest(template=template), self.assertRaises(ValidationError):
                BulkReplacement("(never matches empty)", template, "regex")

    def test_timeout(self) -> None:
        replacement = BulkReplacement(r"(a|aa)+$", "replacement", "regex")
        with self.assertRaisesMessage(ValidationError, "timed out"):
            replacement.replace("a" * 100 + "!")


if TYPE_CHECKING:
    from weblate.auth.models import User


class BulkEditConcurrencyTest(RepoTestMixin, TransactionTestCase):
    def setUp(self) -> None:
        Language.objects.flush_object_cache()
        self.addCleanup(Language.objects.flush_object_cache)
        clear_users_cache()
        self.addCleanup(clear_users_cache)
        self.clone_test_repos()
        super().setUp()
        self.component = self.create_component()
        self.user = get_test_actor(self)
        self.czech = self.component.translation_set.get(
            language_code="cs"
        ).unit_set.get(source="Hello, world!\n")
        self.german = self.component.translation_set.get(
            language_code="de"
        ).unit_set.get(source="Hello, world!\n")

    def test_source_flag_edits_serialize_before_locking_siblings(self) -> None:
        entered = Event()
        release = Event()
        pids: Queue[int] = Queue()
        original = Unit.update_extra_flags

        def update(unit: Unit, flags: str, user: User, save: bool = True) -> None:
            if not entered.is_set():
                entered.set()
                if not release.wait(timeout=10):
                    self.fail("First flag update was not released")
            original(unit, flags, user, save=save)

        def perform(unit_id: int, flags: str) -> int:
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids.put(cursor.fetchone()[0])
                component = Component.objects.get(pk=self.component.pk)
                return bulk_perform(
                    self.user,
                    Unit.objects.filter(pk=unit_id),
                    query="",
                    target_state=-1,
                    add_flags=flags,
                    remove_flags="",
                    add_labels=component.project.label_set.none(),
                    remove_labels=component.project.label_set.none(),
                    project=component.project,
                    components=[component],
                    enforce_permissions=False,
                )
            finally:
                connection.close()

        with (
            patch.object(Unit, "update_extra_flags", update),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first = executor.submit(perform, self.czech.pk, "max-length:80")
            pids.get(timeout=10)
            try:
                self.assertTrue(entered.wait(timeout=10))
                second = executor.submit(perform, self.german.pk, "check-glossary")
                pid = pids.get(timeout=10)
                deadline = monotonic() + 4
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT cardinality(pg_blocking_pids(%s)) > 0", [pid]
                        )
                        if cursor.fetchone()[0]:
                            break
                    sleep(0.01)
                else:
                    self.fail("Second bulk edit did not wait for a row lock")
            finally:
                release.set()
            self.assertEqual(first.result(timeout=10), 1)
            self.assertEqual(second.result(timeout=10), 1)
        source = Unit.objects.get(pk=self.czech.source_unit.pk)
        self.assertIn("max-length:80", source.extra_flags)
        self.assertIn("check-glossary", source.extra_flags)
