# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from filelock import FileLock

from weblate.utils.lock import WeblateLock
from weblate.vcs.base import Repository, RepositoryLock, get_repository_lock_key

if TYPE_CHECKING:
    from weblate.trans.models import Component


class RepositoryLockTest(SimpleTestCase):
    def test_default_redis_lock_uses_scope_and_key(self) -> None:
        redis_lock_factory = MagicMock(return_value=SimpleNamespace())

        with (
            patch("weblate.utils.lock.is_redis_cache", return_value=True),
            patch(
                "weblate.utils.lock.cache",
                SimpleNamespace(lock=redis_lock_factory),
            ),
        ):
            lock = WeblateLock(
                scope="vcs:api:throttle",
                key="github",
                slug="ignored",
                timeout=5,
                origin="project/component",
            )

        redis_lock_factory.assert_called_once_with(
            key="lock:vcs:api:throttle:github",
            blocking=True,
            timeout=3600,
            blocking_timeout=5,
            thread_local=True,
        )
        self.assertEqual(lock.name, "lock:vcs:api:throttle:github")

    def test_default_file_lock_uses_locks_dir(self) -> None:
        with (
            TemporaryDirectory() as temp_dir,
            self.settings(DATA_DIR=temp_dir),
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
        ):
            lock = WeblateLock(
                scope="repository",
                key=1,
                slug="component",
                timeout=5,
                origin="project/component",
            )

        self.assertEqual(
            lock.name, Path(temp_dir, "locks", "repository-1.lock").as_posix()
        )

    def test_default_file_lock_escapes_scope_and_key(self) -> None:
        with (
            TemporaryDirectory() as temp_dir,
            self.settings(DATA_DIR=temp_dir),
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
        ):
            lock = WeblateLock(
                scope="vcs:api:throttle",
                key="project/main",
                slug="ignored",
                timeout=5,
                origin="project/component",
            )

        self.assertEqual(
            lock.name,
            Path(
                temp_dir, "locks", "vcs%3Aapi%3Athrottle-project%2Fmain.lock"
            ).as_posix(),
        )

    def test_reused_lock_stays_reentrant(self) -> None:
        with (
            TemporaryDirectory() as lock_path,
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            patch.object(FileLock, "acquire", autospec=True) as acquire,
            patch.object(FileLock, "release", autospec=True) as release,
        ):
            first_lock = WeblateLock(
                lock_path=lock_path,
                scope="repository",
                key=1,
                slug="component",
                timeout=5,
                origin="project/component",
            )
            second_lock = WeblateLock(
                lock_path=lock_path,
                scope="repository",
                key=1,
                slug="component",
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

        acquire.assert_called_once()
        self.assertEqual(
            sum(
                call.kwargs.get("force", False) is False
                for call in release.call_args_list
            ),
            1,
        )

    def test_lock_override_is_rejected_for_different_lock_name(self) -> None:
        with (
            TemporaryDirectory() as lock_path,
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
        ):
            first_lock = WeblateLock(
                lock_path=lock_path,
                scope="repository",
                key=1,
                slug="component",
                timeout=5,
                origin="project/component",
            )
            second_lock = WeblateLock(
                lock_path=lock_path,
                scope="repository",
                key=2,
                slug="other-component",
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
        with (
            TemporaryDirectory() as lock_path,
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            patch.object(FileLock, "acquire", autospec=True),
            patch.object(FileLock, "release", autospec=True),
        ):
            first_lock = WeblateLock(
                lock_path=lock_path,
                scope="repository",
                key=1,
                slug="component",
                timeout=5,
                origin="project/component",
            )
            second_lock = WeblateLock(
                lock_path=lock_path,
                scope="repository",
                key=1,
                slug="component",
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

    def test_component_repository_lock_name_is_stable_across_path_changes(self) -> None:
        with (
            TemporaryDirectory() as temp_dir,
            self.settings(DATA_DIR=temp_dir),
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
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
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
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

        self.assertEqual(
            first.lock.name,
            Path(
                temp_dir,
                "locks",
                f"repository-{get_repository_lock_key(first_path.as_posix(), first.component)}.lock",
            ).as_posix(),
        )
        self.assertEqual(
            second.lock.name,
            Path(
                temp_dir,
                "locks",
                f"repository-{get_repository_lock_key(second_path.as_posix(), second.component)}.lock",
            ).as_posix(),
        )
        self.assertNotEqual(first.lock.name, second.lock.name)
