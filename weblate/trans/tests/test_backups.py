# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for data exports."""

import os
from unittest import SkipTest
from zipfile import ZipFile

from django.core.files import File
from django.db import connection
from django.urls import reverse

from weblate.checks.models import Check
from weblate.screenshots.models import Screenshot
from weblate.trans.backups import ProjectBackup
from weblate.trans.models import Comment, Project, Suggestion, Unit, Vote
from weblate.trans.tasks import cleanup_project_backups
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file

TEST_SCREENSHOT = get_test_file("screenshot.png")
TEST_BACKUP = get_test_file("projectbackup-4.14.zip")
TEST_INVALID = get_test_file("invalid.zip")


class BackupsTest(ViewTestCase):
    CREATE_GLOSSARIES: bool = True

    def test_create_backup(self):
        # Additional content to test on backups
        label = self.project.label_set.create(name="Label", color="navy")
        unit = self.component.source_translation.unit_set.first()
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

        backup = ProjectBackup()
        backup.backup_project(self.project)

        self.assertTrue(os.path.exists(backup.filename))

        with ZipFile(backup.filename, "r") as zipfile:
            files = set(zipfile.namelist())
            self.assertIn("weblate-backup.json", files)
            self.assertIn("components/test.json", files)
            self.assertIn("components/glossary.json", files)
            self.assertIn("vcs/test/.git/index", files)
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

    def test_restore_4_14(self):
        if not connection.features.can_return_rows_from_bulk_insert:
            raise SkipTest("Not supported")
        restore = ProjectBackup(TEST_BACKUP)
        restore.validate()
        restored = restore.restore(
            project_name="Restored", project_slug="restored", user=self.user
        )
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

    def test_cleanup(self):
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

    def test_views(self):
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
        self.assertContains(response, b"PK")

    def test_view_restore(self):
        if not connection.features.can_return_rows_from_bulk_insert:
            raise SkipTest("Not supported")
        self.user.is_superuser = True
        self.user.save()
        with open(TEST_INVALID, "rb") as handle:
            response = self.client.post(
                reverse("create-project-import"),
                {
                    "zipfile": handle,
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
