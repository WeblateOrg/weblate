# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for management views."""

import os.path

from django.core import mail
from django.urls import reverse

from weblate.lang.models import Language
from weblate.trans.models import Announcement, Category, Component, Project, Translation
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.data import data_dir
from weblate.utils.files import remove_tree
from weblate.utils.stats import ProjectLanguage


class RemovalTest(ViewTestCase):
    def test_translation(self) -> None:
        self.make_manager()
        url = reverse("remove", kwargs=self.kw_translation)
        response = self.client.post(url, {"confirm": ""}, follow=True)
        self.assertContains(
            response, "The slug does not match the one marked for deletion!"
        )
        response = self.client.post(url, {"confirm": "test/test/cs"}, follow=True)
        self.assertContains(response, "The translation has been removed.")

    def test_component(self) -> None:
        self.make_manager()
        url = reverse("remove", kwargs=self.kw_component)
        response = self.client.post(url, {"confirm": ""}, follow=True)
        self.assertContains(
            response, "The slug does not match the one marked for deletion!"
        )
        response = self.client.post(url, {"confirm": "test/test"}, follow=True)
        self.assertContains(
            response, "The translation component was scheduled for removal."
        )

    def test_project(self) -> None:
        self.make_manager()
        url = reverse("remove", kwargs={"path": self.project.get_url_path()})
        response = self.client.post(url, {"confirm": ""}, follow=True)
        self.assertContains(
            response, "The slug does not match the one marked for deletion!"
        )
        response = self.client.post(url, {"confirm": "test"}, follow=True)
        self.assertContains(response, "The project was scheduled for removal.")

    def test_project_language(self) -> None:
        self.make_manager()
        self.assertEqual(Translation.objects.count(), 4)
        url = reverse("remove", kwargs={"path": [self.project.slug, "-", "cs"]})
        response = self.client.post(url, {"confirm": ""}, follow=True)
        self.assertContains(
            response, "The slug does not match the one marked for deletion!"
        )
        response = self.client.post(url, {"confirm": "test/-/cs"}, follow=True)
        self.assertContains(response, "A language in the project was removed.")
        self.assertEqual(Translation.objects.count(), 3)


class RenameTest(ViewTestCase):
    def test_denied(self) -> None:
        self.assertNotContains(
            self.client.get(self.project.get_absolute_url()), "#organize"
        )
        self.assertNotContains(
            self.client.get(self.component.get_absolute_url()), "#organize"
        )
        response = self.client.post(
            reverse("rename", kwargs={"path": self.project.get_url_path()}),
            {"project": self.project.pk, "slug": "xxxx", "name": self.project.name},
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {"project": self.project.pk, "slug": "xxxx", "name": self.component.name},
        )
        self.assertEqual(response.status_code, 403)

        other = Project.objects.create(name="Other", slug="other")
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {
                "project": other.pk,
                "slug": self.component.slug,
                "name": self.component.name,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_move_component(self) -> None:
        self.make_manager()
        other = Project.objects.create(name="Other project", slug="other")
        # Other project should be visible as target for moving
        self.assertContains(
            self.client.get(self.component.get_absolute_url()),
            "Other project",
        )
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {
                "project": other.pk,
                "slug": self.component.slug,
                "name": self.component.name,
            },
        )
        self.assertRedirects(response, "/projects/other/test/")
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.project.slug, "other")
        self.assertIsNotNone(component.repository.last_remote_revision)

    def test_rename_invalid(self) -> None:
        url = self.component.get_absolute_url()
        Component.objects.filter(pk=self.component.id).update(filemask="invalid/*.po")
        self.make_manager()
        self.assertContains(self.client.get(url), "#organize")
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {"project": self.project.pk, "slug": "xxxx", "name": self.component.name},
            follow=True,
        )
        self.assertRedirects(response, f"{url}#organize")
        self.assertContains(
            response,
            "Could not change Test/Test due to an outstanding issue in its settings:",
        )

    def test_rename_component(self) -> None:
        self.make_manager()
        original_url = self.component.get_absolute_url()
        self.assertContains(self.client.get(original_url), "#organize")
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {"project": self.project.pk, "slug": "xxxx", "name": self.component.name},
        )
        self.assertRedirects(response, "/projects/test/xxxx/")
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.slug, "xxxx")
        self.assertIsNotNone(component.repository.last_remote_revision)
        response = self.client.get(component.get_absolute_url())
        self.assertContains(response, "/projects/test/xxxx/")

        # Test rename redirect for the old name in middleware
        response = self.client.get(original_url)
        self.assertRedirects(response, component.get_absolute_url(), status_code=301)

    def test_rename_project(self) -> None:
        # Remove stale dir from previous tests
        target = os.path.join(data_dir("vcs"), "xxxx")
        if os.path.exists(target):
            remove_tree(target)
        self.make_manager()
        self.assertContains(
            self.client.get(self.project.get_absolute_url()), "#organize"
        )
        response = self.client.post(
            reverse("rename", kwargs={"path": self.project.get_url_path()}),
            {"slug": "xxxx", "name": self.project.name},
        )
        self.assertRedirects(response, "/projects/xxxx/")
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.slug, "xxxx")
        for component in project.component_set.iterator():
            self.assertIsNotNone(component.repository.last_remote_revision)
            response = self.client.get(component.get_absolute_url())
            self.assertContains(response, "/projects/xxxx/")

        # Test rename redirect in middleware
        response = self.client.get(self.project.get_absolute_url())
        self.assertRedirects(response, project.get_absolute_url(), status_code=301)

    def test_rename_project_conflict(self) -> None:
        # Test rename conflict
        self.make_manager()
        Project.objects.create(name="Other project", slug="other")
        response = self.client.post(
            reverse("rename", kwargs={"path": self.project.get_url_path()}),
            {"slug": "other", "name": self.project.name},
            follow=True,
        )
        self.assertContains(response, "Project with this URL slug already exists.")

    def test_rename_component_conflict(self) -> None:
        # Test rename conflict
        self.make_manager()
        self.create_link_existing()
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {"project": self.project.pk, "slug": "test2", "name": self.component.name},
            follow=True,
        )
        self.assertContains(
            response,
            "Component or category with the same URL slug already exists at this level.",
        )


class AnnouncementTest(ViewTestCase):
    data = {"message": "Announcement testing", "severity": "warning"}
    outbox = 0

    def perform_test(self, url) -> None:
        response = self.client.post(url, self.data, follow=True)
        self.assertEqual(response.status_code, 403)
        self.make_manager()
        # Add second user to receive notifications
        self.project.add_user(self.anotheruser, "Administration")
        czech = Language.objects.get(code="cs")
        self.anotheruser.profile.languages.add(czech)

        response = self.client.post(url, self.data, follow=True)
        self.assertContains(response, self.data["message"])
        self.assertEqual(len(mail.outbox), self.outbox)

    def test_translation(self) -> None:
        url = reverse("announcement", kwargs=self.kw_translation)
        self.perform_test(url)

    def test_component(self) -> None:
        url = reverse("announcement", kwargs=self.kw_component)
        self.perform_test(url)

    def test_project(self) -> None:
        url = reverse("announcement", kwargs={"path": self.project.get_url_path()})
        self.perform_test(url)

    def test_project_language(self) -> None:
        project_language = ProjectLanguage(
            project=self.project, language=Language.objects.get(code="cs")
        )
        url = reverse("announcement", kwargs={"path": project_language.get_url_path()})
        self.perform_test(url)

    def test_category(self) -> None:
        category = Category(
            project=self.project, name="Test Category", slug="test-category"
        )
        category.save()
        url = reverse("announcement", kwargs={"path": category.get_url_path()})
        self.perform_test(url)

    def test_delete(self) -> None:
        self.test_project()
        message = Announcement.objects.all()[0]
        self.client.post(reverse("announcement-delete", kwargs={"pk": message.pk}))
        self.assertEqual(Announcement.objects.count(), 0)

    def test_delete_deny(self) -> None:
        message = Announcement.objects.create(message="test")
        self.client.post(reverse("announcement-delete", kwargs={"pk": message.pk}))
        self.assertEqual(Announcement.objects.count(), 1)


class AnnouncementNotifyTest(AnnouncementTest):
    data = {"message": "Announcement testing", "severity": "warning", "notify": "1"}
    outbox = 1
