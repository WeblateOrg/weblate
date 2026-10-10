# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from django.conf import settings
from django.contrib.messages import get_messages
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TransactionTestCase

from weblate.trans.models import Component, Unit
from weblate.trans.recovery import recover_checkout, reset_with_recovery
from weblate.trans.tests.test_views import ComponentTestCase
from weblate.trans.tests.utils import RepoTestMixin
from weblate.utils.data import data_path
from weblate.utils.files import remove_tree
from weblate.utils.state import STATE_TRANSLATED
from weblate.vcs.base import (
    RepositoryError,
    RepositoryInternalError,
    get_repository_error_diagnoses,
)
from weblate.vcs.git import GitRepository, SubversionRepository
from weblate.vcs.models import VCS_REGISTRY


class CheckoutPathTest(SimpleTestCase):
    def test_reconstruction_requires_absent_checkout_or_git_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "checkout"
            repository = GitRepository(str(root))
            self.assertTrue(repository.checkout_is_missing())
            root.mkdir()
            self.assertTrue(repository.checkout_is_missing())
            git_dir = root / ".git"
            git_dir.mkdir()
            self.assertFalse(repository.checkout_is_missing())
            git_dir.rmdir()
            git_dir.symlink_to("missing-metadata", target_is_directory=True)
            self.assertFalse(repository.checkout_is_missing())

    def test_truncated_index_has_invalid_checkout_diagnosis(self) -> None:
        self.assertIn(
            {"code": "checkout_invalid"},
            get_repository_error_diagnoses("fatal: index file smaller than expected"),
        )

    def test_missing_command_checkout_has_recovery_diagnosis(self) -> None:
        with TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "missing"
            with self.assertRaises(RepositoryInternalError) as raised:
                GitRepository._popen(  # ruff: ignore[private-member-access]
                    ["status"], cwd=str(checkout)
                )
        self.assertEqual(raised.exception.code, "repository_checkout_missing")
        self.assertEqual(raised.exception.diagnoses, [{"code": "checkout_missing"}])

    def test_occupied_checkout_configuration_is_invalid(self) -> None:
        with TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "checkout"
            checkout.write_text("occupied")
            repository = GitRepository(str(checkout))
            with self.assertRaises(RepositoryInternalError) as raised:
                repository.check_config()
        self.assertEqual(raised.exception.code, "repository_checkout_invalid")

    def test_dangling_git_directory_configuration_is_invalid(self) -> None:
        with TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "checkout"
            checkout.mkdir()
            (checkout / ".git").symlink_to("missing-metadata", target_is_directory=True)
            repository = GitRepository(str(checkout))
            with self.assertRaises(RepositoryInternalError) as raised:
                repository.check_config()
        self.assertEqual(raised.exception.code, "repository_checkout_invalid")

    def test_recovery_rejects_escaping_path(self) -> None:
        with TemporaryDirectory() as temporary, self.assertRaises(RepositoryError):
            GitRepository.recovery_checkout_path(Path(temporary), "../outside.po")

    def test_recovery_rejects_symlink_to_git_metadata(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "metadata-alias").symlink_to(".git", target_is_directory=True)
            with self.assertRaises(RepositoryError):
                GitRepository.recovery_checkout_path(root, "metadata-alias/config")

    def test_recovery_allows_internal_symlinks(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "working-files"
            target.mkdir()
            (root / "working-alias").symlink_to(
                "working-files", target_is_directory=True
            )
            self.assertEqual(
                GitRepository.recovery_checkout_path(root, "working-alias/file"),
                root / "working-alias/file",
            )

    def test_recovery_rejects_external_absolute_symlink(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "checkout"
            root.mkdir()
            (root / "external").symlink_to(Path(temporary) / "outside")
            with self.assertRaises(RepositoryError):
                GitRepository.recovery_checkout_path(root, "external")

    def test_recovery_reports_symlink_resolution_loop(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(Path, "resolve", side_effect=RuntimeError("Symlink loop")),
                self.assertRaises(RepositoryError),
            ):
                GitRepository.recovery_checkout_path(root, "loop")

    def test_git_svn_skips_checkout_recovery(self) -> None:
        with TemporaryDirectory() as temporary:
            repository = SubversionRepository(str(Path(temporary) / "missing"))
            component = cast("Component", SimpleNamespace(repository=repository))
            with (
                patch.object(
                    repository,
                    "checkout_is_missing",
                    side_effect=AssertionError("Unexpected checkout validation"),
                ),
                recover_checkout(component) as reconstructed,
            ):
                self.assertFalse(reconstructed)


class RepositoryRecoveryTest(ComponentTestCase):
    def create_component(self) -> Component:
        return self.create_po_new_base(new_lang="add")

    def create_recovery_link(self) -> Component:
        return self.create_link_existing()

    def test_reset_reapply_missing_checkout(self) -> None:
        unit = self.get_translation().unit_set.order_by("pk")[0]
        Unit.objects.filter(pk=unit.pk).update(
            target="Recovered translation", state=STATE_TRANSLATED
        )
        count = self.component.translation_set.count()
        remove_tree(self.component.full_path)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        self.assertTrue(cast("GitRepository", self.component.repository).is_valid())
        unit.refresh_from_db()
        self.component.drop_template_store_cache()
        self.assertEqual(unit.target, "Recovered translation")
        self.assertEqual(self.component.translation_set.count(), count)
        translation = unit.translation
        translation.component = self.component
        self.assertEqual(
            translation.load_store().find_unit(unit.context, unit.source)[0].target,
            unit.target,
        )

    def test_discard_does_not_reconstruct_missing_checkout(self) -> None:
        remove_tree(self.component.full_path)
        with patch.object(type(self.component.repository), "clone_from") as clone:
            self.assertFalse(self.component.do_reset(self.get_request()))
        clone.assert_not_called()

    def test_missing_git_directory_is_preserved(self) -> None:
        path = Path(self.component.full_path)
        remove_tree(path / ".git")
        sentinel = path / "untracked-data"
        sentinel.write_text("keep me")
        recovery_root = data_path("repository-recovery") / str(self.component.pk)
        before = set(recovery_root.iterdir()) if recovery_root.exists() else set()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        preserved = set(recovery_root.iterdir()) - before
        self.assertEqual(len(preserved), 1)
        self.assertEqual(
            (next(iter(preserved)) / "untracked-data").read_text(), "keep me"
        )

    def test_dangling_checkout_symlink_is_not_reconstructed(self) -> None:
        path = Path(self.component.full_path)
        remove_tree(path)
        path.symlink_to("missing-checkout", target_is_directory=True)
        with patch.object(type(self.component.repository), "clone_from") as clone:
            self.assertFalse(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        clone.assert_not_called()
        self.assertTrue(path.is_symlink())

    def test_recovery_can_stage_next_to_checkout(self) -> None:
        path = Path(self.component.full_path)
        remove_tree(path / ".git")
        before = set(path.parent.iterdir())
        with (
            patch("weblate.trans.recovery.get_repo_temp_dir", return_value=path.parent),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        preserved = set(path.parent.iterdir()) - before
        self.assertEqual(len(preserved), 1)
        self.assertFalse((next(iter(preserved)) / ".git").exists())

    def test_failed_reapply_keeps_original_and_database(self) -> None:
        path = Path(self.component.full_path)
        remove_tree(path / ".git")
        original_units = list(
            self.component.source_translation.unit_set.values_list(
                "pk", "source", "target"
            )
        )
        with patch(
            "weblate.trans.models.Component.restore_pending_translation_files",
            side_effect=RepositoryError(1, "Cannot restore file"),
        ):
            request = self.get_request()
            self.assertFalse(self.component.do_reset(request, keep_changes=True))
        self.assertFalse((path / ".git" / "config").exists())
        self.assertFalse((path / ".git").exists())
        self.assertEqual(
            list(
                self.component.source_translation.unit_set.values_list(
                    "pk", "source", "target"
                )
            ),
            original_units,
        )
        self.assertTrue(
            any(
                "Cannot restore file" in str(message)
                for message in get_messages(request)
            )
        )

    def test_failure_after_replacement_restores_original(self) -> None:
        path = Path(self.component.full_path)
        remove_tree(path / ".git")
        with (
            self.component.repository.lock.without_recovery(),
            self.component.repository.lock,
            self.assertRaisesMessage(RepositoryError, "later failure"),
            recover_checkout(self.component),
        ):
            self.assertTrue((path / ".git" / "HEAD").exists())
            raise RepositoryError(1, "later failure")
        self.assertFalse((path / ".git").exists())

    def test_missing_checkout_configuration_is_repository_error(self) -> None:
        remove_tree(self.component.full_path)
        raised = self.assertRaises(RepositoryError)
        with raised, self.component.repository.lock:
            self.component.repository.check_config()
        self.assertEqual(raised.exception.diagnoses, [{"code": "checkout_missing"}])

    def test_malformed_config_is_not_reconstructed(self) -> None:
        (Path(self.component.full_path) / ".git" / "config").write_text("[invalid\n")
        with patch.object(type(self.component.repository), "clone_from") as clone:
            self.assertFalse(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        clone.assert_not_called()

    def test_config_directory_is_not_reconstructed(self) -> None:
        config = Path(self.component.full_path) / ".git" / "config"
        config.unlink()
        config.mkdir()
        with patch.object(type(self.component.repository), "clone_from") as clone:
            self.assertFalse(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        clone.assert_not_called()
        self.assertTrue(config.is_dir())

    def test_truncated_index_is_not_reconstructed(self) -> None:
        (Path(self.component.full_path) / ".git" / "index").write_bytes(b"bad")
        with patch.object(type(self.component.repository), "clone_from") as clone:
            self.component.do_reset(self.get_request(), keep_changes=True)
        clone.assert_not_called()

    def test_recovery_restores_push_destination(self) -> None:
        if self.component.is_repo_local:
            self.skipTest("Local repository has no push destination")
        push_url = "ssh://git@example.com/project.git"
        self.component.push = push_url
        remove_tree(self.component.full_path)
        with (
            self.component.repository.lock.without_recovery(),
            self.component.repository.lock,
            recover_checkout(self.component) as reconstructed,
        ):
            self.assertTrue(reconstructed)
            self.assertEqual(
                cast("GitRepository", self.component.repository).get_config(
                    "remote.origin.pushurl"
                ),
                push_url,
            )

    def test_missing_origin_is_not_reconstructed(self) -> None:
        if self.component.is_repo_local:
            self.skipTest("Local repository has no origin")
        with self.component.repository.lock:
            self.component.repository.execute(
                ["remote", "remove", "origin"], remote_op="none"
            )
        with patch.object(type(self.component.repository), "clone_from") as clone:
            self.component.do_reset(self.get_request(), keep_changes=True)
        clone.assert_not_called()

    def test_wrong_origin_url_is_not_reconstructed(self) -> None:
        if self.component.is_repo_local:
            self.skipTest("Local repository has no origin")
        repository = cast("GitRepository", self.component.repository)
        with repository.lock:
            repository.execute(
                ["remote", "set-url", "origin", "https://example.com/wrong.git"],
                remote_op="none",
            )
        with patch.object(type(self.component.repository), "clone_from") as clone:
            self.component.do_reset(self.get_request(), keep_changes=True)
        clone.assert_not_called()

    def test_recovery_restores_gerrit_remote(self) -> None:
        if self.component.is_repo_local or "gerrit" not in VCS_REGISTRY:
            self.skipTest("Gerrit repository is not available")
        push_url = "ssh://git@example.com/project.git"
        self.component.vcs = "gerrit"
        self.component.push = push_url
        self.component.drop_repository_cache()
        remove_tree(self.component.full_path)
        with (
            self.component.repository.lock.without_recovery(),
            self.component.repository.lock,
            recover_checkout(self.component) as reconstructed,
        ):
            self.assertTrue(reconstructed)
            self.assertEqual(
                cast("GitRepository", self.component.repository).get_config(
                    "remote.gerrit.url"
                ),
                push_url,
            )
            self.assertEqual(
                cast("GitRepository", self.component.repository).get_config(
                    "gitreview.username"
                ),
                "git",
            )

    def test_filesystem_access_failure_does_not_reconstruct(self) -> None:
        with (
            patch.object(
                self.component.repository,
                "checkout_is_missing",
                side_effect=PermissionError("Permission denied"),
            ),
            patch.object(type(self.component.repository), "clone_from") as clone,
        ):
            self.assertFalse(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        clone.assert_not_called()

    def test_clone_failure_leaves_missing_checkout_and_translations(self) -> None:
        original_count = Unit.objects.filter(
            translation__component=self.component
        ).count()
        remove_tree(self.component.full_path)
        with patch.object(
            type(self.component.repository),
            "clone_from",
            side_effect=RepositoryError(1, "Clone failed"),
        ):
            self.assertFalse(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(),
            original_count,
        )
        self.assertFalse(Path(self.component.full_path).exists())

    def test_missing_config_can_be_created_during_configuration(self) -> None:
        config = Path(self.component.full_path) / ".git" / "config"
        config.unlink()
        with self.component.repository.lock:
            self.component.repository.check_config()
        self.assertTrue(config.is_file())
        self.assertEqual(
            cast("GitRepository", self.component.repository).get_config("gc.auto"),
            "0",
        )

    def test_recovery_preserves_linked_translations(self) -> None:
        linked = self.create_recovery_link()
        unit = linked.translation_set.get(language__code="cs").unit_set.order_by("pk")[
            0
        ]
        Unit.objects.filter(pk=unit.pk).update(
            target="Recovered linked translation", state=STATE_TRANSLATED
        )
        remove_tree(self.component.full_path)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Recovered linked translation")
        translation = unit.translation
        self.assertEqual(
            translation.load_store().find_unit(unit.context, unit.source)[0].target,
            unit.target,
        )


class LocalRepositoryRecoveryTest(RepositoryRecoveryTest):
    def create_component(self) -> Component:
        return self.make_local(self.create_tbx())

    def make_local(self, component: Component) -> Component:
        # The shared remote fixture deliberately includes escaping symlinks.
        root = Path(component.full_path)
        for filename in root.rglob("*"):
            if filename.is_symlink() and not filename.resolve().is_relative_to(root):
                filename.unlink()
        Component.objects.filter(pk=component.pk).update(vcs="local", repo="local:")
        component.refresh_from_db()
        component.drop_repository_cache()
        return component

    def create_recovery_link(self) -> Component:
        root = Path(self.component.full_path)
        copytree(root / "tbx", root / "linked-tbx")
        return self.create_link_existing(file_format="tbx", filemask="linked-tbx/*.tbx")

    def test_missing_required_template_keeps_database(self) -> None:
        linked = self.create_link_existing()
        count = Unit.objects.filter(translation__component=linked).count()
        remove_tree(self.component.full_path)
        request = self.get_request()
        self.assertFalse(self.component.do_reset(request, keep_changes=True))
        self.assertEqual(
            Unit.objects.filter(translation__component=linked).count(), count
        )
        self.assertTrue(
            any(
                "could not reapply" in str(message).lower()
                for message in get_messages(request)
            )
        )

    def test_recovery_keeps_surviving_working_files(self) -> None:
        path = Path(self.component.full_path)
        remove_tree(path / ".git")
        sentinel = path / "untracked-data"
        sentinel.write_text("keep me")
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        self.assertEqual(sentinel.read_text(), "keep me")
        repository = cast("GitRepository", self.component.repository)
        self.assertEqual(
            repository.execute(
                ["ls-files", "--error-unmatch", "--", "untracked-data"],
                remote_op="none",
                needs_lock=False,
            ).strip(),
            "untracked-data",
        )
        with repository.lock:
            repository.cleanup_files()
        self.assertEqual(sentinel.read_text(), "keep me")
        self.assertEqual(
            cast("GitRepository", self.component.repository).get_config("user.name"),
            settings.DEFAULT_COMMITER_NAME,
        )

    def test_recovery_keeps_weblate_tmp_working_file(self) -> None:
        path = Path(self.component.full_path)
        remove_tree(path / ".git")
        working = path / "weblate-tmp" / "note.txt"
        working.parent.mkdir()
        working.write_text("keep me")
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        self.assertEqual(working.read_text(), "keep me")

    def test_recovery_keeps_readme_symlink(self) -> None:
        path = Path(self.component.full_path)
        remove_tree(path / ".git")
        sentinel = path / "working-file"
        sentinel.write_text("keep me")
        readme = path / "README.md"
        if readme.exists() or readme.is_symlink():
            readme.unlink()
        readme.symlink_to(sentinel.name)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        self.assertTrue(readme.is_symlink())
        self.assertEqual(readme.read_text(), "keep me")

    def test_recovery_keeps_absolute_internal_symlink(self) -> None:
        path = Path(self.component.full_path)
        remove_tree(path / ".git")
        sentinel = path / "working-file"
        sentinel.write_text("keep me")
        link = path / "absolute-link"
        link.symlink_to(sentinel.resolve())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.read_text(), "keep me")


class LocalTemplateReapplyTest(LocalRepositoryRecoveryTest):
    def create_component(self) -> Component:
        return self.make_local(self.create_json_mono())


class RemoteSourceRecoveryTest(ComponentTestCase):
    def create_component(self) -> Component:
        return self.create_json_mono()

    def test_recovery_does_not_recreate_strings_removed_upstream(self) -> None:
        unit = self.get_translation().unit_set.order_by("pk")[0]
        filenames = []
        for translation in self.component.translation_set.all():
            if not translation.filename:
                continue
            store = translation.load_store()
            store.delete_unit(store.find_unit(unit.context, unit.source)[0].unit)
            store.save()
            filenames.append(translation.filename)
        with self.component.repository.lock:
            self.component.repository.commit("Remove obsolete strings", files=filenames)
            self.component.repository.push(self.component.push_branch)
        remove_tree(self.component.full_path)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )
        self.component.drop_template_store_cache()
        for translation in self.component.translation_set.all():
            if translation.filename:
                self.assertNotIn(
                    unit.context,
                    {item.context for item in translation.load_store().content_units},
                )


class RepositoryRecoveryTransactionTest(RepoTestMixin, TransactionTestCase):
    def setUp(self) -> None:
        self.clone_test_repos()
        super().setUp()
        self.component = self.create_component()
        self.path = Path(self.component.full_path)
        remove_tree(self.path / ".git")

    def reset_with_callback(self, *args: object, **kwargs: object) -> str:
        Component.objects.filter(pk=self.component.pk).update(name="Recovered")
        transaction.on_commit(self.fail_followup)
        return self.component.repository.last_revision

    @staticmethod
    def fail_followup() -> None:
        msg = "Follow-up failed"
        raise RuntimeError(msg)

    def test_followup_failure_keeps_committed_checkout(self) -> None:
        with (
            patch.object(
                Component,
                "reset_repository_to_remote",
                side_effect=self.reset_with_callback,
            ),
            self.assertRaisesMessage(RuntimeError, "Follow-up failed"),
        ):
            reset_with_recovery(self.component, None, None, keep_changes=True)
        self.component.refresh_from_db()
        self.assertEqual(self.component.name, "Recovered")
        self.assertTrue((self.path / ".git" / "HEAD").exists())
        self.assertTrue(cast("GitRepository", self.component.repository).is_valid())

    def test_commit_failure_restores_original_checkout(self) -> None:
        original_name = self.component.name
        with (
            patch.object(
                Component,
                "reset_repository_to_remote",
                side_effect=self.reset_with_callback,
            ),
            patch.object(
                connection, "_commit", side_effect=IntegrityError("Commit failed")
            ),
            self.assertRaisesMessage(IntegrityError, "Commit failed"),
        ):
            reset_with_recovery(self.component, None, None, keep_changes=True)
        self.component.refresh_from_db()
        self.assertEqual(self.component.name, original_name)
        self.assertFalse((self.path / ".git").exists())

    def test_nested_transaction_does_not_replace_checkout(self) -> None:
        original_name = self.component.name
        with (
            patch.object(type(self.component.repository), "clone_from") as clone,
            self.assertRaisesMessage(
                RuntimeError, "durable atomic block cannot be nested"
            ),
            transaction.atomic(),
        ):
            reset_with_recovery(self.component, None, None, keep_changes=True)
        clone.assert_not_called()
        self.component.refresh_from_db()
        self.assertEqual(self.component.name, original_name)
        self.assertFalse((self.path / ".git").exists())
