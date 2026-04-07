# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for categories."""

import os
from contextlib import ExitStack
from unittest.mock import call, patch

from django.urls import reverse

from weblate.lang.models import get_default_lang
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Category, Component, ComponentLink, Project
from weblate.trans.removal import RemovalBatch
from weblate.trans.tasks import category_removal
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.stats import GlobalStats


class CategoriesTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.add_user(self.user, "Administration")

    def add_and_organize(self) -> Category:
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
        response = self.client.get(category_url)
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
        ComponentLink.objects.create(component=self.component, project=project)

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
        self.client.post(
            reverse("rename", kwargs=self.kw_component),
            {
                "project": self.project.pk,
                "category": category.pk,
                "slug": self.component.slug,
                "name": self.component.name,
            },
            follow=True,
        )
        self.component.refresh_from_db()
        self.assertEqual(self.component.category, category)

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

    def test_category_removal_batches_linked_alert_updates(self) -> None:
        category = Category.objects.create(
            project=self.project, name="Category test", slug="testcat"
        )
        first = self.create_link_existing(
            name="Linked A", slug="linked-a", category=category
        )
        second = self.create_link_existing(
            name="Linked B", slug="linked-b", category=category
        )

        with patch.object(Component, "update_alerts", autospec=True) as update_alerts:
            category_removal(category.pk, self.user.pk)

        self.assertFalse(
            Component.objects.filter(pk__in=[first.pk, second.pk]).exists()
        )
        update_alerts.assert_called_once_with(self.component)

    def test_category_removal_skips_propagation_for_removed_components(self) -> None:
        category = Category.objects.create(
            project=self.project, name="Category test", slug="testcat"
        )
        first = self.create_po(
            project=self.project,
            name="Category A",
            slug="category-a",
            category=category,
        )
        second = self.create_po(
            project=self.project,
            name="Category B",
            slug="category-b",
            category=category,
        )
        first.allow_translation_propagation = True
        first.save(update_fields=["allow_translation_propagation"])
        second.allow_translation_propagation = True
        second.save(update_fields=["allow_translation_propagation"])

        with patch.object(
            Component, "schedule_update_checks", autospec=True
        ) as schedule:
            category_removal(category.pk, self.user.pk)

        self.assertEqual(
            [call(self.component), call(self.component)],
            schedule.call_args_list,
        )

    def test_category_removal_skips_propagation_for_cascaded_linked_components(
        self,
    ) -> None:
        category = Category.objects.create(
            project=self.project, name="Category test", slug="testcat"
        )
        self.component.category = category
        self.component.save()

        linked = self.create_link_existing(name="Linked A", slug="linked-a")
        linked.allow_translation_propagation = True
        linked.save(update_fields=["allow_translation_propagation"])

        other = self.create_po(
            project=self.project,
            name="Category A",
            slug="category-a",
            category=category,
        )
        other.allow_translation_propagation = True
        other.save(update_fields=["allow_translation_propagation"])

        with patch.object(
            Component, "schedule_update_checks", autospec=True
        ) as schedule:
            category_removal(category.pk, self.user.pk)

        schedule.assert_not_called()

    def test_category_removal_batches_parent_stats_updates(self) -> None:
        category = Category.objects.create(
            project=self.project, name="Category test", slug="testcat"
        )
        for pos in range(2):
            self.create_po(
                project=self.project,
                name=f"Category {pos}",
                slug=f"category-{pos}",
                category=category,
            )

        collected: list[set[str]] = []
        executed: list[str] = []
        original_flush = RemovalBatch.flush

        def record_flush(batch_self: RemovalBatch) -> None:
            collected.append(set(batch_self.stats_to_update))
            with ExitStack() as stack:
                for stats in batch_self.stats_to_update.values():
                    stack.enter_context(
                        patch.object(
                            stats,
                            "update_stats",
                            side_effect=lambda stats=stats: executed.append(
                                stats.cache_key
                            ),
                        )
                    )
                original_flush(batch_self)

        with patch.object(
            RemovalBatch, "flush", autospec=True, side_effect=record_flush
        ):
            category_removal(category.pk, self.user.pk)

        self.assertEqual(1, len(collected))
        self.assertEqual(
            {category.stats.cache_key, GlobalStats().cache_key},
            collected[0],
        )
        self.assertEqual(collected[0], set(executed))
        self.assertEqual(
            2,
            self.project.change_set.filter(
                action=ActionEvents.REMOVE_COMPONENT
            ).count(),
        )

    def test_category_removal_updates_nested_categories_before_global(self) -> None:
        category = Category.objects.create(
            project=self.project, name="Parent category", slug="parent"
        )
        child = Category.objects.create(
            project=self.project,
            category=category,
            name="Child category",
            slug="child",
        )
        self.create_po(
            project=self.project,
            name="Category A",
            slug="category-a",
            category=child,
        )

        executed: list[str] = []
        original_flush = RemovalBatch.flush

        def record_flush(batch_self: RemovalBatch) -> None:
            with ExitStack() as stack:
                for stats in batch_self.stats_to_update.values():
                    stack.enter_context(
                        patch.object(
                            stats,
                            "update_stats",
                            side_effect=lambda stats=stats: executed.append(
                                stats.cache_key
                            ),
                        )
                    )
                original_flush(batch_self)

        with patch.object(
            RemovalBatch, "flush", autospec=True, side_effect=record_flush
        ):
            category_removal(category.pk, self.user.pk)

        self.assertLess(
            executed.index(child.stats.cache_key),
            executed.index(category.stats.cache_key),
        )
        self.assertLess(
            executed.index(category.stats.cache_key),
            executed.index(GlobalStats().cache_key),
        )
