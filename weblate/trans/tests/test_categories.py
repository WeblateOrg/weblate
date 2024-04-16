# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for categories."""

import os

from django.urls import reverse

from weblate.lang.models import get_default_lang
from weblate.trans.models import Category, Component, Project
from weblate.trans.tests.test_views import ViewTestCase


class CategoriesTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.add_user(self.user, "Administration")

    def add_and_organize(self):
        response = self.client.post(
            reverse("add-category", kwargs={"path": self.project.get_url_path()}),
            {"name": "Test category", "slug": "test-cat"},
            follow=True,
        )
        category_url = reverse(
            "show", kwargs={"path": [*self.project.get_url_path(), "test-cat"]}
        )
        category = Category.objects.get()
        self.assertRedirects(response, category_url)
        self.assertContains(response, "Nothing to list here.")
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {
                "project": self.project.pk,
                "category": category.pk,
                "slug": self.component.slug,
                "name": self.component.name,
            },
            follow=True,
        )
        new_component_url = reverse(
            "show",
            kwargs={
                "path": [*self.project.get_url_path(), "test-cat", self.component.slug]
            },
        )
        self.assertRedirects(response, new_component_url)
        self.client.get(category_url)
        self.assertNotContains(response, "Nothing to list here.")
        return category

    def test_add_move(self) -> None:
        category = self.add_and_organize()

        # Category/language view
        response = self.client.get(
            reverse(
                "show",
                kwargs={"path": [*self.project.get_url_path(), "test-cat", "-", "cs"]},
            )
        )
        self.assertContains(response, "Test category")

        response = self.client.post(
            reverse("rename", kwargs={"path": category.get_url_path()}),
            {
                "name": "Other",
                "slug": "renamed",
                "project": category.project.id,
                "category": "",
            },
            follow=True,
        )
        self.assertNotContains(response, "Nothing to list here.")
        category = Category.objects.get()
        self.assertEqual(category.name, "Other")
        self.assertEqual(category.slug, "renamed")

        # Add nested
        response = self.client.post(
            reverse("add-category", kwargs={"path": category.get_url_path()}),
            {"name": "Test category", "slug": "test-cat"},
            follow=True,
        )
        self.assertContains(response, "Nothing to list here.")
        # Another toplevel with same name
        response = self.client.post(
            reverse("add-category", kwargs={"path": self.project.get_url_path()}),
            {"name": "Test category", "slug": "test-cat"},
            follow=True,
        )
        self.assertContains(response, "Nothing to list here.")
        new_category = self.project.category_set.get(category=None, slug="test-cat")

        # Move to other category
        response = self.client.post(
            reverse("rename", kwargs={"path": category.get_url_path()}),
            {
                "project": self.project.pk,
                "category": new_category.pk,
                "name": category.name,
                "slug": category.slug,
            },
            follow=True,
        )
        self.assertContains(response, "Test category")
        self.assertNotContains(response, "Nothing to list here.")

        # Delete
        response = self.client.post(
            reverse("remove", kwargs={"path": new_category.get_url_path()}),
            {"confirm": new_category.full_slug},
            follow=True,
        )
        self.assertRedirects(response, self.project.get_absolute_url())
        self.assertEqual(Component.objects.count(), 0)

    def test_move_project(self) -> None:
        project = Project.objects.create(name="other", slug="other")
        category = Category.objects.create(
            name="Test category", slug="oc", project=self.project
        )
        # Move to other project
        response = self.client.post(
            reverse("rename", kwargs={"path": category.get_url_path()}),
            {
                "project": project.pk,
                "category": "",
                "name": category.name,
                "slug": category.slug,
            },
            follow=True,
        )
        self.assertContains(response, "Test category")
        self.assertContains(response, "Nothing to list here.")

    def test_move_wrong(self) -> None:
        project = Project.objects.create(name="other", slug="other")
        category = Category.objects.create(name="other", slug="oc", project=project)
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {
                "project": self.project.pk,
                "category": category.pk,
                "slug": self.component.slug,
                "name": self.component.name,
            },
            follow=True,
        )
        self.assertContains(
            response, "Error in parameter category: Select a valid choice."
        )

    def test_paths(self) -> None:
        old_path = self.component.full_path
        self.assertTrue(os.path.exists(old_path))
        self.assertTrue(
            os.path.exists(
                self.component.translation_set.get(language_code="cs").get_filename()
            )
        )

        # Add it to category
        category = Category.objects.create(
            project=self.project, name="Category test", slug="testcat"
        )
        old_category_path = category.full_path
        self.assertTrue(os.path.exists(old_category_path))
        self.component.category = category
        self.component.save()
        category_path = self.component.full_path
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(category_path))
        self.assertTrue(
            os.path.exists(
                self.component.translation_set.get(language_code="cs").get_filename()
            )
        )

        # Rename category
        category.slug = "other"
        category.acting_user = self.user
        category.save()
        self.assertFalse(os.path.exists(old_category_path))
        self.assertTrue(os.path.exists(category.full_path))

        component = Component.objects.get(pk=self.component.pk)
        self.assertFalse(os.path.exists(old_path))
        self.assertFalse(os.path.exists(category_path))
        self.assertTrue(os.path.exists(component.full_path))
        self.assertTrue(
            os.path.exists(
                component.translation_set.get(language_code="cs").get_filename()
            )
        )

    def test_create(self) -> None:
        # Make superuser, otherwise user can not create due to no valid billing
        self.user.is_superuser = True
        self.user.save()

        category = Category.objects.create(
            project=self.project, name="Category test", slug="testcat"
        )
        response = self.client.post(
            reverse("create-component-vcs"),
            {
                "name": "Create Component",
                "slug": "create-component",
                "project": self.project.pk,
                "vcs": "git",
                "repo": self.component.get_repo_link_url(),
                "file_format": "po",
                "filemask": "po/*.po",
                "new_base": "po/project.pot",
                "new_lang": "add",
                "language_regex": "^[^.]+$",
                "source_language": get_default_lang(),
                "category": category.pk,
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_move_category(self) -> None:
        category = self.add_and_organize()

        project = Project.objects.create(name="other", slug="other")
        project.add_user(self.user, "Administration")

        response = self.client.post(
            reverse("rename", kwargs={"path": category.get_url_path()}),
            {
                "project": project.pk,
                "category": "",
                "name": category.name,
                "slug": category.slug,
            },
            follow=True,
        )
        self.assertRedirects(
            response,
            reverse(
                "show",
                kwargs={"path": [*project.get_url_path(), "test-cat"]},
            ),
        )
        self.assertTrue(project.component_set.exists())
        self.assertFalse(category.component_set.filter(project=self.project).exists())

    def test_move_linked_component(self) -> None:
        project = Project.objects.create(name="other", slug="other")
        self.component.links.add(project)

        response = self.client.post(
            reverse("add-category", kwargs={"path": self.project.get_url_path()}),
            {"name": "Test category", "slug": "test-cat"},
            follow=True,
        )
        category_url = reverse(
            "show", kwargs={"path": [*self.project.get_url_path(), "test-cat"]}
        )
        category = Category.objects.get()
        self.assertRedirects(response, category_url)
        self.assertContains(response, "Nothing to list here.")
        response = self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {
                "project": self.project.pk,
                "category": category.pk,
                "slug": self.component.slug,
                "name": self.component.name,
            },
            follow=True,
        )
        self.assertContains(response, "Categorized component can not be shared.")

    def test_move_category_linked_repo(self) -> None:
        component = self.create_link_existing()
        self.assertEqual(component.repo, "weblate://test/test")

        category = self.add_and_organize()

        component.refresh_from_db()
        self.assertEqual(component.repo, "weblate://test/test-cat/test")

        self.client.post(
            reverse("rename", kwargs={"path": category.get_url_path()}),
            {
                "project": self.project.pk,
                "category": "",
                "name": category.name,
                "slug": "test-rename",
            },
            follow=True,
        )

        component.refresh_from_db()
        self.assertEqual(component.repo, "weblate://test/test-rename/test")

        project = Project.objects.create(name="other", slug="other")
        project.add_user(self.user, "Administration")

        category = Category.objects.get()
        self.client.post(
            reverse("rename", kwargs={"path": category.get_url_path()}),
            {
                "project": project.pk,
                "category": "",
                "name": category.name,
                "slug": category.slug,
            },
            follow=True,
        )

        component.refresh_from_db()
        self.assertEqual(component.repo, "weblate://other/test-rename/test")
