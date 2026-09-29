# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from weblate.utils.lock import WeblateLock, WeblateLockTimeoutError
from weblate.vcs.base import RepositoryLock


class WeblateLockTest(SimpleTestCase):
    def test_lock_uses_postgresql_advisory_lock(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (True,)
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor_context
        database_connection.in_atomic_block = False
        atomic = MagicMock()

        with (
            patch("weblate.utils.lock.connection", database_connection),
            patch("weblate.utils.lock.transaction.atomic", return_value=atomic),
        ):
            lock = WeblateLock(
                scope="repository",
                key=1,
                slug="component",
                timeout=5,
                origin="project/component",
            )
            with lock:
                pass

        cursor.execute.assert_called_once_with(
            "SELECT pg_try_advisory_xact_lock(%s, %s)",
            [1, 1],
        )
        atomic.__enter__.assert_called_once_with()
        atomic.__exit__.assert_called_once_with(None, None, None)

    def test_lock_uses_existing_transaction(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (True,)
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor_context
        database_connection.in_atomic_block = True
        atomic = MagicMock()

        with (
            patch("weblate.utils.lock.connection", database_connection),
            patch("weblate.utils.lock.transaction.atomic", return_value=atomic),
        ):
            lock = WeblateLock(scope="repository", key=1, slug="component")
            with lock:
                pass

        cursor.execute.assert_called_once_with(
            "SELECT pg_try_advisory_xact_lock(%s, %s)",
            [1, 1],
        )
        atomic.assert_not_called()

    def test_reused_lock_stays_reentrant(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (True,)
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor_context
        database_connection.in_atomic_block = False
        atomic = MagicMock()

        with (
            patch("weblate.utils.lock.connection", database_connection),
            patch("weblate.utils.lock.transaction.atomic", return_value=atomic),
        ):
            first_lock = WeblateLock(
                scope="repository",
                key=1,
                slug="component",
                timeout=5,
                origin="project/component",
            )
            second_lock = WeblateLock(
                scope="repository",
                key=1,
                slug="component",
                timeout=5,
                origin="project/component",
            )
            first_repository = SimpleNamespace(
                ensure_lock_session_recovered=lambda: None
            )
            second_repository = SimpleNamespace(
                ensure_lock_session_recovered=lambda: None
            )
            outer_lock = RepositoryLock(first_repository, first_lock)
            inner_lock = RepositoryLock(second_repository, second_lock)

            self.assertTrue(inner_lock.replace_lock_if_matching(outer_lock))
            with outer_lock, inner_lock:
                self.assertTrue(outer_lock.is_locked)
                self.assertTrue(inner_lock.is_locked)

        cursor.execute.assert_called_once_with(
            "SELECT pg_try_advisory_xact_lock(%s, %s)",
            [1, 1],
        )

    def test_lock_override_is_rejected_for_different_lock_name(self) -> None:
        first_lock = WeblateLock(scope="repository", key=1, slug="component")
        second_lock = WeblateLock(scope="repository", key=2, slug="other-component")
        first_repository = SimpleNamespace(ensure_lock_session_recovered=lambda: None)
        second_repository = SimpleNamespace(ensure_lock_session_recovered=lambda: None)
        outer_lock = RepositoryLock(first_repository, first_lock)
        inner_lock = RepositoryLock(second_repository, second_lock)

        self.assertFalse(inner_lock.replace_lock_if_matching(outer_lock))
        self.assertIs(inner_lock.lock_object, second_lock)

    def test_shared_lock_uses_postgresql_advisory_lock(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (True,)
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor_context
        database_connection.in_atomic_block = False
        atomic = MagicMock()

        with (
            patch("weblate.utils.lock.connection", database_connection),
            patch("weblate.utils.lock.transaction.atomic", return_value=atomic),
        ):
            lock = WeblateLock(
                scope="backup:run",
                key=1,
                slug="backup",
                shared=True,
            )
            with lock:
                pass

        cursor.execute.assert_called_once_with(
            "SELECT pg_try_advisory_xact_lock_shared(%s, %s)",
            [9, 1],
        )

    def test_lock_timeout_raises(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (False,)
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor_context
        database_connection.in_atomic_block = False
        atomic = MagicMock()

        with (
            patch("weblate.utils.lock.connection", database_connection),
            patch("weblate.utils.lock.transaction.atomic", return_value=atomic),
            self.assertRaisesRegex(
                WeblateLockTimeoutError,
                "could not be acquired",
            ),
        ):
            lock = WeblateLock(
                scope="repository",
                key=1,
                slug="component",
                timeout=0,
            )
            with lock:
                pass

        cursor.execute.assert_called_once_with(
            "SELECT pg_try_advisory_xact_lock(%s, %s)",
            [1, 1],
        )

    def test_lock_identity_is_stable(self) -> None:
        first = WeblateLock(
            scope="repository",
            key=1,
            slug="component",
        )
        second = WeblateLock(
            scope="repository",
            key=1,
            slug="renamed-component",
        )

        self.assertEqual(first.scope_key, second.scope_key)
        self.assertEqual(first.lock_key, second.lock_key)
        self.assertEqual(first.name, second.name)

    def test_different_lock_keys_are_distinct(self) -> None:
        first = WeblateLock(
            scope="repository",
            key=1,
            slug="component",
        )
        second = WeblateLock(
            scope="repository",
            key=2,
            slug="other-component",
        )

        self.assertEqual(first.scope_key, second.scope_key)
        self.assertNotEqual(first.lock_key, second.lock_key)
