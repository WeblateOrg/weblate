# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for data exports."""

import os
from zipfile import ZipFile

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import skipIfDBFeature, skipUnlessDBFeature
from django.urls import reverse

from weblate.auth.data import SELECTION_MANUAL
from weblate.auth.models import AutoGroup, Group, Role
from weblate.checks.models import Check
from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.trans.backups import ProjectBackup
from weblate.trans.models import Category, Comment, Project, Suggestion, Unit, Vote
from weblate.trans.tasks import cleanup_project_backup_download, cleanup_project_backups
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file

TEST_SCREENSHOT = get_test_file("screenshot.png")
TEST_BACKUP = get_test_file("projectbackup-4.14.zip")
TEST_BACKUP_DUPLICATE = get_test_file("projectbackup-duplicate.zip")


class BackupsTest(ViewTestCase):
    CREATE_GLOSSARIES: bool = True

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
        shot.units.add(unit)

        unit.comment_set.create(
            comment="Test comment",
            user=self.user,
        )
        suggestion = unit.suggestion_set.create(
            target="Suggestion test",
            user=self.user,
        )
        Vote.objects.create(suggestion=suggestion, user=self.user, value=1)
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
            self.assertIn("components/test.json", files)
            self.assertIn("components/glossary.json", files)
            self.assertIn("vcs/my-category/test/.git/index", files)
            self.assertIn("vcs/glossary/.git/index", files)

        restore = ProjectBackup(backup.filename)

        if not connection.features.can_return_rows_from_bulk_insert:
            with self.assertRaises(ValueError):
                restore.validate()
            return

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

    @skipUnlessDBFeature("can_return_rows_from_bulk_insert")
    def test_restore_supported(self) -> None:
        self.assertTrue(connection.features.can_return_rows_from_bulk_insert)

    @skipIfDBFeature("can_return_rows_from_bulk_insert")
    def test_restore_not_supported(self) -> None:
        self.assertFalse(connection.features.can_return_rows_from_bulk_insert)

    @skipUnlessDBFeature("can_return_rows_from_bulk_insert")
    def test_restore_4_14(self) -> None:
        restore = ProjectBackup(TEST_BACKUP)
        restore.validate()
        restore.restore(
            project_name="Restored", project_slug="restored", user=self.user
        )
        self.verify_restored()

    @skipUnlessDBFeature("can_return_rows_from_bulk_insert")
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

    @skipUnlessDBFeature("can_return_rows_from_bulk_insert")
    def test_restore_duplicate(self) -> None:
        restore = ProjectBackup(TEST_BACKUP_DUPLICATE)
        with self.assertRaises(ValueError):
            restore.validate()

    def test_cleanup(self) -> None:
        cleanup_project_backups()
        self.assertLessEqual(len(self.project.list_backups()), 3)
        ProjectBackup().backup_project(self.project)
        cleanup_project_backups()
        self.assertLessEqual(len(self.project.list_backups()), 3)
        ProjectBackup().backup_project(self.project)
        cleanup_project_backups()
        self.assertLessEqual(len(self.project.list_backups()), 3)
        ProjectBackup().backup_project(self.project)
        cleanup_project_backups()
        self.assertLessEqual(len(self.project.list_backups()), 3)
        ProjectBackup().backup_project(self.project)
        self.assertEqual(len(self.project.list_backups()), 4)
        cleanup_project_backups()
        self.assertEqual(len(self.project.list_backups()), 3)
        cleanup_project_backup_download()

    def test_views(self) -> None:
        start = len(self.project.list_backups())
        url = reverse("backups", kwargs=self.kw_project)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(url)
        self.assertRedirects(response, url)
        self.assertEqual(start + 1, len(self.project.list_backups()))
        response = self.client.get(url)
        self.assertNotContains(response, " no backups")

        url = reverse(
            "backups-download",
            kwargs={
                "project": self.project.slug,
                "backup": self.project.list_backups()[0]["name"],
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

    @skipUnlessDBFeature("can_return_rows_from_bulk_insert")
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
