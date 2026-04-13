# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for data exports."""

import json
import os
import tempfile
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from weblate.addons.webhooks import WebhookAddon
from weblate.auth.data import SELECTION_MANUAL
from weblate.auth.models import AutoGroup, Group, Role
from weblate.checks.models import Check
from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.backups import ProjectBackup, list_backups
from weblate.trans.change_display import get_change_history_context
from weblate.trans.models import (
    Category,
    Change,
    Comment,
    Component,
    PendingUnitChange,
    Project,
    Suggestion,
    Unit,
    Vote,
)
from weblate.trans.tasks import cleanup_project_backup_download, cleanup_project_backups
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file

TEST_SCREENSHOT = get_test_file("screenshot.png")
TEST_BACKUP = get_test_file("projectbackup-4.14.zip")
TEST_BACKUP_DUPLICATE = get_test_file("projectbackup-duplicate.zip")
TEST_BACKUP_DUPLICATE_FILES = get_test_file("projectbackup-duplicate-files.zip")


class BackupsTest(ViewTestCase):
    CREATE_GLOSSARIES: bool = True

    def test_backup_creates_history_entry(self) -> None:
        backup = ProjectBackup()

        backup.backup_project(self.project)

        change = self.project.change_set.get(action=ActionEvents.PROJECT_BACKUP)
        self.assertIsNone(change.user)
        self.assertEqual(
            change.details,
            {"backup_filename": backup.relative_filename},
        )
        history_data = get_change_history_context(change)
        self.assertEqual(history_data["description"], "Project backed up")
        self.assertEqual(
            history_data["change_details_fields"][0]["label"],
            "Backup file",
        )
        self.assertIn(
            backup.relative_filename,
            history_data["change_details_fields"][0]["content"],
        )

    def test_backup_creates_history_entry_with_user(self) -> None:
        backup = ProjectBackup()

        backup.backup_project(self.project, self.user)

        change = self.project.change_set.get(action=ActionEvents.PROJECT_BACKUP)
        self.assertEqual(change.user, self.user)
        self.assertEqual(change.author, self.user)

    def test_restore_creates_history_entries(self) -> None:
        backup = ProjectBackup()
        backup.backup_project(self.project)

        restore = ProjectBackup(backup.filename)
        restore.validate()
        restored = restore.restore(
            project_name="Restored", project_slug="restored", user=self.user
        )

        project_change = restored.change_set.get(action=ActionEvents.PROJECT_RESTORE)
        self.assertEqual(project_change.user, self.user)
        self.assertEqual(project_change.author, self.user)
        self.assertEqual(
            project_change.details,
            {
                "backup_timestamp": restore.data["metadata"]["timestamp"],
                "backup_server": restore.data["metadata"]["server"],
                "backup_domain": restore.data["metadata"]["domain"],
            },
        )
        history_data = get_change_history_context(project_change)
        self.assertEqual(history_data["description"], "Project restored")
        self.assertEqual(
            [field["label"] for field in history_data["change_details_fields"]],
            ["Backup created", "Backup server", "Backup domain"],
        )

        component_changes = Change.objects.filter(
            project=restored, action=ActionEvents.COMPONENT_RESTORE
        )
        self.assertEqual(component_changes.count(), restored.component_set.count())
        self.assertEqual(
            {change.details["original_slug"] for change in component_changes},
            {
                ProjectBackup.full_slug_without_project(component)
                for component in self.project.component_set.iterator()
            },
        )
        for change in component_changes:
            self.assertEqual(change.user, self.user)
            self.assertEqual(change.author, self.user)
            self.assertIsNotNone(change.component)
            component_history_data = get_change_history_context(change)
            self.assertEqual(
                component_history_data["description"], "Component restored"
            )
            self.assertEqual(
                component_history_data["change_details_fields"][0]["label"],
                "Original component",
            )

    def test_restore_batches_change_addon_dispatch(self) -> None:
        backup = ProjectBackup()
        backup.backup_project(self.project)
        restore = ProjectBackup(backup.filename)
        restore.validate()
        WebhookAddon.create(
            configuration={
                "webhook_url": "https://example.com/hook",
                "events": [ActionEvents.PROJECT_RESTORE],
            },
            run=False,
        )

        with patch("weblate.addons.tasks.addon_change.delay_on_commit") as mocked_delay:
            restored = restore.restore(
                project_name="Restored", project_slug="restored", user=self.user
            )

        self.assertEqual(mocked_delay.call_count, 2)
        self.assertEqual(
            sorted(len(call.args[0]) for call in mocked_delay.call_args_list),
            [1, restored.component_set.count() + 1],
        )

    def test_create_backup(self) -> None:
        # Create linked component
        self.create_link_existing()
        # Additional content to test on backups
        category = self.project.category_set.create(
            name="My Category", slug="my-category"
        )
        self.component.category = category
        self.component.save()
        label = self.project.label_set.create(name="Label", color="navy")
        unit = self.component.source_translation.unit_set.all()[0]
        unit.labels.add(label)
        shot = Screenshot.objects.create(
            name="Obrazek", translation=self.component.source_translation
        )
        with open(TEST_SCREENSHOT, "rb") as handle:
            shot.image.save("screenshot.png", File(handle))
        shot.add_unit(unit, user=self.user)

        unit.comment_set.create(
            comment="Test comment",
            user=self.user,
        )
        suggestion = unit.suggestion_set.create(
            target="Suggestion test",
            user=self.user,
        )
        Vote.objects.create(suggestion=suggestion, user=self.user, value=1)

        PendingUnitChange.store_unit_change(unit)

        team = Group.objects.create(name="Test group", defining_project=self.project)
        team.roles.set([Role.objects.get(name="Translate")])
        team.admins.add(self.user)
        team.language_selection = SELECTION_MANUAL
        team.languages.set(
            [
                Language.objects.get(code="en"),
                Language.objects.get(code="ru"),
            ]
        )
        AutoGroup(match="^.*$", group=team).save()

        backup = ProjectBackup()
        backup.backup_project(self.project)

        self.assertTrue(os.path.exists(backup.filename))

        with ZipFile(backup.filename, "r") as zipfile:
            files = set(zipfile.namelist())
            self.assertIn("weblate-backup.json", files)
            self.assertIn("components/my-category/test.json", files)
            self.assertIn("components/glossary.json", files)
            self.assertIn("vcs/my-category/test/.git/index", files)
            self.assertIn("vcs/glossary/.git/index", files)

        restore = ProjectBackup(backup.filename)

        restore.validate()

        restored = restore.restore(
            project_name="Restored", project_slug="restored", user=self.user
        )

        self.assertEqual(
            Vote.objects.filter(
                suggestion__unit__translation__component__project=self.project
            ).count(),
            Vote.objects.filter(
                suggestion__unit__translation__component__project=restored
            ).count(),
        )
        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation__component__project=self.project
            ).count(),
            Suggestion.objects.filter(
                unit__translation__component__project=restored
            ).count(),
        )
        self.assertEqual(
            Comment.objects.filter(
                unit__translation__component__project=self.project
            ).count(),
            Comment.objects.filter(
                unit__translation__component__project=restored
            ).count(),
        )
        self.assertEqual(
            Check.objects.filter(
                unit__translation__component__project=self.project
            ).count(),
            Check.objects.filter(
                unit__translation__component__project=restored
            ).count(),
        )
        self.assertEqual(
            set(self.project.label_set.values_list("name", "color")),
            set(restored.label_set.values_list("name", "color")),
        )
        self.assertEqual(
            set(self.project.component_set.values_list("slug", flat=True)),
            set(restored.component_set.values_list("slug", flat=True)),
        )
        self.assertEqual(
            Category.objects.filter(project=self.project).count(),
            Category.objects.filter(project=restored).count(),
        )
        self.assertEqual(
            set(self.project.category_set.values_list("slug", flat=True)),
            set(restored.category_set.values_list("slug", flat=True)),
        )
        self.assertEqual(
            self.project.count_pending_units,
            restored.count_pending_units,
        )
        restored_screenshot = Screenshot.objects.get(
            translation__component__project=restored
        )
        self.assertTrue(
            restored_screenshot.image.storage.exists(restored_screenshot.image.name)
        )
        self.assertGreater(restored_screenshot.image.size, 0)

        restored_team = restored.defined_groups.filter(name=team.name).first()
        self.assertIsNotNone(restored_team)
        self.assertEqual(team.language_selection, restored_team.language_selection)
        self.assertEqual(
            set(team.roles.values_list("name", flat=True)),
            set(restored_team.roles.values_list("name", flat=True)),
        )
        self.assertEqual(
            set(team.admins.values_list("username", flat=True)),
            set(restored_team.admins.values_list("username", flat=True)),
        )
        self.assertEqual(
            set(team.user_set.values_list("username", flat=True)),
            set(restored_team.user_set.values_list("username", flat=True)),
        )
        self.assertEqual(
            set(team.languages.values_list("code", flat=True)),
            set(restored_team.languages.values_list("code", flat=True)),
        )
        self.assertEqual(
            team.components.count(),
            restored_team.components.count(),
        )

        def component_category_mapping(p):
            """Return a mapping of component slugs to component category slugs."""
            return {
                co.slug: co.category.slug if co.category else None
                for co in p.component_set.all()
            }

        self.assertEqual(
            component_category_mapping(self.project),
            component_category_mapping(restored),
        )
        # Verify that Git operations work on restored repos
        restored.do_reset()

    def test_restore_synthesizes_source_translation_check_flags(self) -> None:
        source = self.component.source_translation
        source.check_flags = "strict-same"
        source.save(update_fields=["check_flags"])

        backup = ProjectBackup()
        backup.backup_project(self.project)

        with ZipFile(backup.filename, "r") as zipfile:
            component_file = next(
                path
                for path in zipfile.namelist()
                if path.startswith("components/")
                and path.endswith(f"{self.component.slug}.json")
            )
            component_data = json.loads(zipfile.read(component_file).decode("utf-8"))
        self.assertFalse(
            any(
                "check_flags" in translation
                for translation in component_data["translations"]
            )
        )

        restore = ProjectBackup(backup.filename)
        restore.validate()
        restored = restore.restore(
            project_name="Restored", project_slug="restored", user=self.user
        )

        restored_component = restored.component_set.get(slug=self.component.slug)
        restored_source = restored_component.source_translation

        self.assertEqual(restored_source.check_flags, "read-only")

    def test_create_duplicate(self) -> None:
        def extract_names(qs) -> list[str]:
            return list(qs.order_by("name").values_list("name", flat=True))

        category = self.project.category_set.create(
            name="My Category", slug="my-category"
        )
        self.create_link_existing(name="Test", slug="test", category=category)
        backup = ProjectBackup()
        backup.backup_project(self.project)

        self.assertTrue(os.path.exists(backup.filename))

        restore = ProjectBackup(backup.filename)

        restore.validate()

        restored = restore.restore(
            project_name="Restored", project_slug="restored", user=self.user
        )

        self.assertEqual(
            extract_names(Category.objects.filter(project=self.project)),
            extract_names(Category.objects.filter(project=restored)),
        )
        self.assertEqual(
            extract_names(Component.objects.filter(project=self.project)),
            extract_names(Component.objects.filter(project=restored)),
        )

    def test_restore_4_14(self) -> None:
        restore = ProjectBackup(TEST_BACKUP)
        restore.validate()
        restore.restore(
            project_name="Restored", project_slug="restored", user=self.user
        )
        self.verify_restored()

    def test_restore_requires_validation(self) -> None:
        restore = ProjectBackup(TEST_BACKUP)
        with self.assertRaisesRegex(ValueError, "validated before restore"):
            restore.restore(
                project_name="Restored", project_slug="restored", user=self.user
            )

    def test_restore_cli(self) -> None:
        call_command(
            "import_projectbackup", "Restored", "restored", "testuser", TEST_BACKUP
        )
        self.verify_restored()

    def verify_restored(self) -> None:
        restored = Project.objects.get(slug="restored")
        self.assertEqual(
            16,
            Unit.objects.filter(translation__component__project=restored).count(),
        )
        self.assertEqual(
            1,
            Vote.objects.filter(
                suggestion__unit__translation__component__project=restored
            ).count(),
        )
        self.assertEqual(
            1,
            Suggestion.objects.filter(
                unit__translation__component__project=restored
            ).count(),
        )
        self.assertEqual(
            1,
            Comment.objects.filter(
                unit__translation__component__project=restored
            ).count(),
        )
        self.assertEqual(
            3,
            Check.objects.filter(
                unit__translation__component__project=restored
            ).count(),
        )
        self.assertEqual(
            {("Label", "navy")},
            set(restored.label_set.values_list("name", "color")),
        )

    def test_restore_duplicate(self) -> None:
        restore = ProjectBackup(TEST_BACKUP_DUPLICATE)
        with self.assertRaises(ValueError):
            restore.validate()

    def test_restore_duplicate_files(self) -> None:
        restore = ProjectBackup(TEST_BACKUP_DUPLICATE_FILES)
        with self.assertRaises(ValueError) as ex:
            restore.validate()
        self.assertIn("zip file contains duplicate files", str(ex.exception))

    @override_settings(
        PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_RATIO=5,
        PROJECT_BACKUP_IMPORT_MIN_RATIO_SIZE=10,
        PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE=100,
    )
    def test_restore_zip_bomb_compressed_large_entry(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_handle:
            temp_name = temp_handle.name

        try:
            with (
                ZipFile(TEST_BACKUP, "r") as source_zip,
                ZipFile(temp_name, "w") as zipfile,
            ):
                for item in source_zip.infolist():
                    zipfile.writestr(item, source_zip.read(item.filename))
                zipfile.writestr("payload.bin", b"a" * 5000, compress_type=ZIP_DEFLATED)

            restore = ProjectBackup(temp_name)
            with self.assertRaisesRegex(
                ValueError, "compressed entry that is too large"
            ):
                restore.validate()
        finally:
            os.unlink(temp_name)

    @override_settings(PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE=10)
    def test_restore_low_compression_large_entry_allowed(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_handle:
            temp_name = temp_handle.name

        try:
            with (
                ZipFile(TEST_BACKUP, "r") as source_zip,
                ZipFile(temp_name, "w") as zipfile,
            ):
                for item in source_zip.infolist():
                    zipfile.writestr(item, source_zip.read(item.filename))
                zipfile.writestr(
                    "payload.bin", b"12345678901", compress_type=ZIP_STORED
                )

            restore = ProjectBackup(temp_name)
            restore.validate()
        finally:
            os.unlink(temp_name)

    @override_settings(PROJECT_BACKUP_IMPORT_MAX_MEMBERS=5)
    def test_restore_zip_bomb_too_many_members(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_handle:
            temp_name = temp_handle.name

        try:
            with (
                ZipFile(TEST_BACKUP, "r") as source_zip,
                ZipFile(temp_name, "w") as zipfile,
            ):
                for item in source_zip.infolist():
                    zipfile.writestr(item, source_zip.read(item.filename))
                for idx in range(5):
                    zipfile.writestr(f"extra-{idx}.txt", b"x", compress_type=ZIP_STORED)

            restore = ProjectBackup(temp_name)
            with self.assertRaisesRegex(ValueError, "contains too many entries"):
                restore.validate()
        finally:
            os.unlink(temp_name)

    def test_restore_skips_git_hooks(self) -> None:
        backup = ProjectBackup()
        backup.backup_project(self.project)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_handle:
            temp_name = temp_handle.name

        try:
            with (
                ZipFile(backup.filename, "r") as source_zip,
                ZipFile(temp_name, "w") as target_zip,
            ):
                for item in source_zip.infolist():
                    target_zip.writestr(item, source_zip.read(item.filename))
                target_zip.writestr(
                    "vcs/test/.git/hooks/post-checkout",
                    b"#!/bin/sh\nexit 1\n",
                )

            restore = ProjectBackup(temp_name)
            restore.validate()
            restored = restore.restore(
                project_name="Restored", project_slug="restored", user=self.user
            )
            component = restored.component_set.get(slug="test")
            self.assertFalse(
                os.path.exists(
                    os.path.join(component.full_path, ".git", "hooks", "post-checkout")
                )
            )
            self.assertEqual(
                component.repository.get_config("remote.origin.url"), component.repo
            )
            self.assertEqual(
                component.repository.get_config(f"branch.{component.branch}.remote"),
                "origin",
            )
            self.assertEqual(
                component.repository.get_config(f"branch.{component.branch}.merge"),
                f"refs/heads/{component.branch}",
            )
            restored.do_reset()
        finally:
            os.unlink(temp_name)

    def test_restore_rejects_invalid_screenshot(self) -> None:
        screenshot = Screenshot.objects.create(
            name="Tampered screenshot", translation=self.component.source_translation
        )
        with open(TEST_SCREENSHOT, "rb") as handle:
            screenshot.image.save("screenshot.png", File(handle))

        backup = ProjectBackup()
        backup.backup_project(self.project)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_handle:
            temp_name = temp_handle.name

        try:
            with (
                ZipFile(backup.filename, "r") as source_zip,
                ZipFile(temp_name, "w") as target_zip,
            ):
                for item in source_zip.infolist():
                    data = source_zip.read(item.filename)
                    if item.filename.startswith("screenshots/"):
                        data = b"not an image"
                    target_zip.writestr(item, data)

            restore = ProjectBackup(temp_name)
            restore.validate()
            with self.assertRaises(ValidationError):
                restore.restore(
                    project_name="Restored", project_slug="restored", user=self.user
                )
        finally:
            os.unlink(temp_name)

    def test_cleanup(self) -> None:
        cleanup_project_backups()
        self.assertLessEqual(len(list_backups(self.project)), 3)
        ProjectBackup().backup_project(self.project)
        cleanup_project_backups()
        self.assertLessEqual(len(list_backups(self.project)), 3)
        ProjectBackup().backup_project(self.project)
        cleanup_project_backups()
        self.assertLessEqual(len(list_backups(self.project)), 3)
        ProjectBackup().backup_project(self.project)
        cleanup_project_backups()
        self.assertLessEqual(len(list_backups(self.project)), 3)
        ProjectBackup().backup_project(self.project)
        self.assertEqual(len(list_backups(self.project)), 4)
        cleanup_project_backups()
        self.assertEqual(len(list_backups(self.project)), 3)
        cleanup_project_backup_download()

    def test_views(self) -> None:
        start = len(list_backups(self.project))
        url = reverse("backups", kwargs=self.kw_project)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(url)
        self.assertRedirects(response, url)
        self.assertEqual(start + 1, len(list_backups(self.project)))
        change = self.project.change_set.get(action=ActionEvents.PROJECT_BACKUP)
        self.assertEqual(change.user, self.user)
        self.assertEqual(change.author, self.user)
        response = self.client.get(url)
        self.assertNotContains(response, " no backups")

        url = reverse(
            "backups-download",
            kwargs={
                "project": self.project.slug,
                "backup": list_backups(self.project)[0]["name"],
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        # Testing staticfiles doesn't work, so we emulate this manually
        url = response.url
        self.assertTrue(url.startswith(settings.STATIC_URL))
        filename = url[len(settings.STATIC_URL) :]
        with staticfiles_storage.open(filename, "rb") as handle:
            self.assertEqual(handle.read(2), b"PK")

    def test_view_restore(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("create-project-import"),
            {
                "zipfile": SimpleUploadedFile(
                    "invalid.zip", b"x", content_type="application/zip"
                )
            },
            follow=True,
        )
        self.assertContains(response, "Could not load project backup")

        with open(TEST_BACKUP, "rb") as handle:
            response = self.client.post(
                reverse("create-project-import"),
                {
                    "zipfile": handle,
                },
                follow=True,
            )
            self.assertContains(
                response, "Created on Weblate (example.com) by Weblate 4.14-dev"
            )
            response = self.client.post(
                reverse("create-project-import"),
                {
                    "name": "Import Test",
                    "slug": "import-test",
                },
                follow=True,
            )
            self.assertContains(response, "Import Test")
            project = Project.objects.get(slug="import-test")
            self.assertEqual(project.component_set.count(), 2)
