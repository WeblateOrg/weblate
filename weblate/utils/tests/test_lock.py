# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

from django.db import connection, transaction
from django.test import TransactionTestCase

from weblate.utils.lock import LockScope, WeblateLock
from weblate.vcs.base import Repository, RepositoryLock

if TYPE_CHECKING:
    from weblate.trans.models import Component


class RepositoryLockTest(TransactionTestCase):
    def test_session_readers_and_transaction_lifetimes(self) -> None:
        other = connection.copy()
        self.addCleanup(other.close)
        lock = WeblateLock(scope=LockScope.REPOSITORY, key=1, timeout=0)
        with other.cursor() as cursor, transaction.atomic():
            with lock.shared_reader():
                cursor.execute(
                    "SELECT pg_try_advisory_lock_shared(%s, 1)",
                    [LockScope.REPOSITORY.value],
                )
                self.assertTrue(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT pg_advisory_unlock_shared(%s, 1)",
                    [LockScope.REPOSITORY.value],
                )
                cursor.execute(
                    "SELECT pg_try_advisory_lock(%s, 1)", [LockScope.REPOSITORY.value]
                )
                self.assertFalse(cursor.fetchone()[0])
            with lock, lock:
                self.assertTrue(lock.is_locked)
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s, 1)", [LockScope.REPOSITORY.value]
            )
            self.assertTrue(cursor.fetchone()[0])
            cursor.execute(
                "SELECT pg_advisory_unlock(%s, 1)", [LockScope.REPOSITORY.value]
            )
            lock.acquire_transaction()
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s, 1)", [LockScope.REPOSITORY.value]
            )
            self.assertFalse(cursor.fetchone()[0])
        with other.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s, 1)", [LockScope.REPOSITORY.value]
            )
            self.assertTrue(cursor.fetchone()[0])

    def test_reused_lock_stays_reentrant(self) -> None:
        first_lock = WeblateLock(
            scope=LockScope.REPOSITORY,
            key=1,
            timeout=5,
            origin="project/component",
        )
        second_lock = WeblateLock(
            scope=LockScope.REPOSITORY,
            key=1,
            timeout=5,
            origin="project/component",
        )
        first_repository = cast(
            "Repository",
            SimpleNamespace(ensure_lock_session_recovered=lambda: None),
        )
        second_repository = cast(
            "Repository",
            SimpleNamespace(ensure_lock_session_recovered=lambda: None),
        )
        outer_lock = RepositoryLock(first_repository, first_lock)
        inner_lock = RepositoryLock(second_repository, second_lock)
        self.assertTrue(inner_lock.replace_lock_if_matching(outer_lock))

        with outer_lock, inner_lock:
            self.assertTrue(outer_lock.is_locked)
            self.assertTrue(inner_lock.is_locked)

        self.assertFalse(outer_lock.is_locked)

    def test_lock_override_is_rejected_for_different_lock_name(self) -> None:
        first_lock = WeblateLock(
            scope=LockScope.REPOSITORY,
            key=1,
            timeout=5,
            origin="project/component",
        )
        second_lock = WeblateLock(
            scope=LockScope.REPOSITORY,
            key=2,
            timeout=5,
            origin="project/other-component",
        )
        first_repository = cast(
            "Repository",
            SimpleNamespace(ensure_lock_session_recovered=lambda: None),
        )
        second_repository = cast(
            "Repository",
            SimpleNamespace(ensure_lock_session_recovered=lambda: None),
        )
        outer_lock = RepositoryLock(first_repository, first_lock)
        inner_lock = RepositoryLock(second_repository, second_lock)

        self.assertFalse(inner_lock.replace_lock_if_matching(outer_lock))
        self.assertIs(inner_lock.lock_object, second_lock)

    def test_reused_lock_preserves_pending_recovery(self) -> None:
        first_lock = WeblateLock(
            scope=LockScope.REPOSITORY,
            key=1,
            timeout=5,
            origin="project/component",
        )
        second_lock = WeblateLock(
            scope=LockScope.REPOSITORY,
            key=1,
            timeout=5,
            origin="project/component",
        )
        first_repository = cast(
            "Repository",
            SimpleNamespace(ensure_lock_session_recovered=lambda: None),
        )
        second_repository = cast(
            "Repository",
            SimpleNamespace(ensure_lock_session_recovered=lambda: None),
        )
        outer_lock = RepositoryLock(first_repository, first_lock)
        inner_lock = RepositoryLock(second_repository, second_lock)

        with outer_lock:
            self.assertTrue(inner_lock.replace_lock_if_matching(outer_lock))
            self.assertTrue(inner_lock.begin_recovery())
            inner_lock.finish_recovery()

    def test_reused_lock_shares_active_recovery_skip(self) -> None:
        first_lock = WeblateLock(
            scope=LockScope.REPOSITORY,
            key=1,
            timeout=5,
            origin="project/component",
        )
        second_lock = WeblateLock(
            scope=LockScope.REPOSITORY,
            key=1,
            timeout=5,
            origin="project/component",
        )
        first_repository = cast(
            "Repository",
            SimpleNamespace(ensure_lock_session_recovered=lambda: None),
        )
        second_recovery = MagicMock()
        second_repository = cast(
            "Repository",
            SimpleNamespace(ensure_lock_session_recovered=second_recovery),
        )
        outer_lock = RepositoryLock(first_repository, first_lock)
        inner_lock = RepositoryLock(second_repository, second_lock)

        with outer_lock.without_recovery():
            self.assertTrue(inner_lock.replace_lock_if_matching(outer_lock))
            with inner_lock:
                pass

        second_recovery.assert_not_called()

        with inner_lock:
            pass

        second_recovery.assert_called_once_with()

    def test_component_repository_lock_name_is_stable_across_path_changes(self) -> None:
        with (
            TemporaryDirectory() as temp_dir,
            self.settings(DATA_DIR=temp_dir),
        ):
            Path(temp_dir, "home").mkdir()
            first_path = Path(temp_dir, "vcs", "project", "component")
            second_path = Path(temp_dir, "vcs", "renamed-project", "renamed-component")
            first = Repository(
                first_path.as_posix(),
                branch="main",
                component=cast(
                    "Component",
                    SimpleNamespace(pk=1, full_slug="project/component"),
                ),
                local=True,
            )
            second = Repository(
                second_path.as_posix(),
                branch="main",
                component=cast(
                    "Component",
                    SimpleNamespace(pk=1, full_slug="renamed/project/component"),
                ),
                local=True,
            )

        self.assertEqual(first.lock.name, second.lock.name)

    def test_unsaved_component_repository_lock_name_uses_checkout_path(self) -> None:
        with (
            TemporaryDirectory() as temp_dir,
            self.settings(DATA_DIR=temp_dir),
        ):
            Path(temp_dir, "home").mkdir()
            first_path = Path(temp_dir, "vcs", "project", "component")
            second_path = Path(temp_dir, "vcs", "other-project", "component")
            first = Repository(
                first_path.as_posix(),
                branch="main",
                component=cast(
                    "Component",
                    SimpleNamespace(pk=None, full_slug="project/component"),
                ),
                local=True,
            )
            second = Repository(
                second_path.as_posix(),
                branch="main",
                component=cast(
                    "Component",
                    SimpleNamespace(pk=None, full_slug="other-project/component"),
                ),
                local=True,
            )

        self.assertNotEqual(first.lock.name, second.lock.name)
