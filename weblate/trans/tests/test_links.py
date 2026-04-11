# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for component links."""

from __future__ import annotations

from django.urls import reverse

from weblate.trans.models import Category, Project
from weblate.trans.models.component import ComponentLink
from weblate.trans.tests.test_views import ViewTestCase


class ComponentLinkTestCase(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.other = Project.objects.create(name="Other", slug="other")
        self.link = ComponentLink.objects.create(
            component=self.component, project=self.other
        )

    def test_list(self) -> None:
        response = self.client.get(self.project.get_absolute_url())
        self.assertContains(response, self.component.get_absolute_url())
        response = self.client.get(self.other.get_absolute_url())
        self.assertContains(response, self.component.get_absolute_url())

    def test_shared_with_source_category_visible_at_root(self) -> None:
        """Shared component with a category in its source project should still appear at root of target project when the link has no category."""
        source_cat = Category.objects.create(
            name="Source Cat", slug="source-cat", project=self.project
        )
        self.component.category = source_cat
        self.component.save(update_fields=["category"])

        # self.link has no category - component should appear at other's root
        response = self.client.get(self.other.get_absolute_url())
        self.assertContains(response, self.component.get_absolute_url())

        # Categorize the link - component should move from root to category
        self.make_manager()
        target_cat = Category.objects.create(
            name="Target Cat", slug="target-cat", project=self.other
        )
        self.link.category = target_cat
        self.link.save(update_fields=["category"])

        # Not at root
        response = self.client.get(self.other.get_absolute_url())
        self.assertNotContains(response, self.component.get_absolute_url())

        # Visible under the target category
        response = self.client.get(target_cat.get_absolute_url())
        self.assertContains(response, self.component.get_absolute_url())

    def test_categorized_shared_not_at_root(self) -> None:
        """Shared component categorized in one project must not appear at that project's root, even when shared uncategorized in another."""
        self.make_manager()
        self.assertIsNone(self.component.category)

        # Share into a third project with no category
        third = Project.objects.create(name="Third", slug="third")
        ComponentLink.objects.create(component=self.component, project=third)

        cat = Category.objects.create(
            name="Target Cat", slug="target-cat", project=self.other
        )
        self.link.category = cat
        self.link.save(update_fields=["category"])

        # 'other' root should NOT show it (categorized there)
        response = self.client.get(self.other.get_absolute_url())
        self.assertNotContains(response, self.component.get_absolute_url())

        # 'other' category SHOULD show it
        response = self.client.get(cat.get_absolute_url())
        self.assertContains(response, self.component.get_absolute_url())

        # 'third' root SHOULD show it (uncategorized link)
        response = self.client.get(third.get_absolute_url())
        self.assertContains(response, self.component.get_absolute_url())

    def test_stats(self) -> None:
        project = Project.objects.get(pk=self.project.pk)
        other = Project.objects.get(pk=self.other.pk)

        self.maxDiff = None
        self.assertEqual(project.stats.get_data(), other.stats.get_data())

    def test_stats_edit(self) -> None:
        self.other.stats.force_load()
        start_data = self.other.stats.get_data()

        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

        project = Project.objects.get(pk=self.project.pk)
        other = Project.objects.get(pk=self.other.pk)

        self.maxDiff = None
        self.assertEqual(project.stats.get_data(), other.stats.get_data())
        self.assertNotEqual(start_data, other.stats.get_data())

    def test_stats_languages_count_with_shared_components(self) -> None:
        """Project stats should count distinct languages across own and shared components."""
        own_component = self.create_po(project=self.other, name="Other")

        shared_language_ids = set(
            self.component.translation_set.values_list("language_id", flat=True)
        )
        own_language_ids = set(
            own_component.translation_set.values_list("language_id", flat=True)
        )
        self.assertEqual(shared_language_ids, own_language_ids)

        other = Project.objects.get(pk=self.other.pk)
        self.assertEqual(other.get_languages_count(), len(shared_language_ids))
        self.assertEqual(other.stats.languages, len(shared_language_ids))

    def test_labels(self) -> None:
        self.other.label_set.create(name="test other", color="navy")
        self.project.label_set.create(name="test project", color="navy")
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

        project = Project.objects.get(pk=self.project.pk)
        other = Project.objects.get(pk=self.other.pk)

        self.maxDiff = None
        self.assertEqual(project.stats.get_data(), other.stats.get_data())

    def test_cycle(self) -> None:
        ignore_keys = ("last_changed", "stats_timestamp")

        def compare_stats(one: dict, other: dict, *, equals: bool = True) -> None:
            for key in ignore_keys:
                for data in (one, other):
                    data.pop(key)
            if equals:
                self.assertEqual(one, other)
            else:
                self.assertNotEqual(one, other)

        third_project = Project.objects.create(name="Third", slug="third")

        self.other.label_set.create(name="test other", color="navy")
        self.project.label_set.create(name="test project", color="navy")
        third_project.label_set.create(name="test third", color="navy")

        self.maxDiff = None
        other_component = self.create_po(project=self.other)

        third_component = self.create_po(project=third_project)

        ComponentLink.objects.create(component=other_component, project=third_project)
        ComponentLink.objects.create(component=third_component, project=self.project)

        # The stats should now match as all the components are same and
        # each project has two of them
        project = Project.objects.get(pk=self.project.pk)
        other = Project.objects.get(pk=self.other.pk)
        third_project = Project.objects.get(pk=third_project.pk)

        compare_stats(project.stats.get_data(), other.stats.get_data())
        compare_stats(project.stats.get_data(), third_project.stats.get_data())

        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

        project = Project.objects.get(pk=self.project.pk)
        other = Project.objects.get(pk=self.other.pk)
        third_project = Project.objects.get(pk=third_project.pk)

        compare_stats(project.stats.get_data(), other.stats.get_data())
        # This one should be different as it does not have the shared component
        compare_stats(
            project.stats.get_data(), third_project.stats.get_data(), equals=False
        )

    def test_categorize_shared_component(self) -> None:
        """Shared component can be placed into a category in the target project."""
        self.make_manager()
        cat = Category.objects.create(
            name="Test Category", slug="test-cat", project=self.other
        )

        self.client.post(
            reverse(
                "component-link-categories",
                kwargs={"path": self.component.get_url_path()},
            ),
            {"link_id": self.link.pk, "category": cat.pk},
        )

        self.link.refresh_from_db()
        self.assertEqual(self.link.category, cat)

        # Component should appear under category
        components = cat.get_child_components_access(self.user)
        self.assertIn(self.component, components)

        cat = Category.objects.get(pk=cat.pk)
        child_objects = cat.stats.get_child_objects()
        child_ids = set(child_objects.values_list("pk", flat=True))
        self.assertIn(self.component.pk, child_ids)

        # The categorized shared component should be excluded from root
        categorized_ids = ComponentLink.objects.filter(
            project=self.other, category__isnull=False
        ).values_list("component_id", flat=True)
        self.assertIn(self.component.pk, list(categorized_ids))

        self.client.post(
            reverse(
                "component-link-categories",
                kwargs={"path": self.component.get_url_path()},
            ),
            {"link_id": self.link.pk, "category": ""},
        )
        self.link.refresh_from_db()
        self.assertIsNone(self.link.category)

    def test_view_reject_wrong_project_category(self) -> None:
        """Cannot assign a category from a different project to a link."""
        self.make_manager()
        wrong_cat = Category.objects.create(
            name="Wrong Category", slug="wrong-cat", project=self.project
        )
        self.client.post(
            reverse(
                "component-link-categories",
                kwargs={"path": self.component.get_url_path()},
            ),
            {"link_id": self.link.pk, "category": wrong_cat.pk},
        )
        self.link.refresh_from_db()
        self.assertIsNone(self.link.category)

    def test_view_add_delete_link(self) -> None:
        """POST to component-link-add creates a new link and component-link-delete removes it."""
        self.make_manager()
        third = Project.objects.create(name="Third", slug="third")
        self.client.post(
            reverse(
                "component-link-add",
                kwargs={"path": self.component.get_url_path()},
            ),
            {"link_add-project": third.pk, "link_add-category": ""},
        )
        self.assertTrue(
            ComponentLink.objects.filter(
                component=self.component, project=third
            ).exists()
        )

        self.client.post(
            reverse(
                "component-link-delete",
                kwargs={"path": self.component.get_url_path()},
            ),
            {"link_id": self.link.pk},
        )
        self.assertFalse(ComponentLink.objects.filter(pk=self.link.pk).exists())

        cat = Category.objects.create(
            name="Test Category", slug="test-cat", project=self.other
        )
        self.client.post(
            reverse(
                "component-link-add",
                kwargs={"path": self.component.get_url_path()},
            ),
            {"link_add-project": self.other.pk, "link_add-category": cat.pk},
        )
        link = ComponentLink.objects.get(component=self.component, project=self.other)
        self.assertEqual(link.category, cat)

    def test_view_add_link_duplicate(self) -> None:
        """Adding a link to an already linked project does not create duplicate."""
        self.make_manager()
        self.client.post(
            reverse(
                "component-link-add",
                kwargs={"path": self.component.get_url_path()},
            ),
            {"link_add-project": self.other.pk, "link_add-category": ""},
        )
        self.assertEqual(
            ComponentLink.objects.filter(
                component=self.component, project=self.other
            ).count(),
            1,
        )

    def test_view_delete_link_invalid(self) -> None:
        """Deleting a non-existent link returns 404."""
        self.make_manager()
        response = self.client.post(
            reverse(
                "component-link-delete",
                kwargs={"path": self.component.get_url_path()},
            ),
            {"link_id": 99999},
        )
        self.assertEqual(response.status_code, 404)

    def test_category_deletion_clears_link(self) -> None:
        """Deleting a category sets link.category to NULL."""
        cat = Category.objects.create(
            name="Test Category", slug="test-cat", project=self.other
        )
        self.link.category = cat
        self.link.save()

        cat.delete()
        self.link.refresh_from_db()
        self.assertIsNone(self.link.category)

    def test_category_stats(self) -> None:
        """Category stats and languages should include shared components."""
        cat = Category.objects.create(
            name="Test Category", slug="test-cat", project=self.other
        )

        child_ids = set(cat.stats.get_child_objects().values_list("pk", flat=True))
        self.assertNotIn(self.component.pk, child_ids)

        self.link.category = cat
        self.link.save()

        cat = Category.objects.get(pk=cat.pk)
        child_ids = set(cat.stats.get_child_objects().values_list("pk", flat=True))
        self.assertIn(self.component.pk, child_ids)

    def test_category_languages_include_shared(self) -> None:
        """An empty category with only a shared component should show that component's languages and translations in the language tab."""
        cat = Category.objects.create(
            name="Empty Cat", slug="empty-cat", project=self.other
        )
        self.assertEqual(cat.component_set.count(), 0)
        self.assertEqual(len(cat.languages), 0)

        self.link.category = cat
        self.link.save()

        cat = Category.objects.get(pk=cat.pk)
        self.assertNotEqual(len(cat.languages), 0)

        comp_languages = set(
            self.component.translation_set.values_list("language_id", flat=True)
        )
        cat_language_ids = {lang.pk for lang in cat.languages}
        self.assertTrue(comp_languages.issubset(cat_language_ids))

        language_stats = cat.stats.get_language_stats()
        self.assertGreater(len(language_stats), 0)
        for stat in language_stats:
            self.assertGreater(stat.all, 0)

    def test_add_link_requires_managed_project(self) -> None:
        """Cannot add a link to a project the user does not manage."""
        self.project.add_user(self.user, "Administration")
        third = Project.objects.create(name="Third", slug="third")
        add_url = reverse(
            "component-link-add",
            kwargs={"path": self.component.get_url_path()},
        )

        # Cannot link to non-managed project
        self.client.post(
            add_url, {"link_add-project": third.pk, "link_add-category": ""}
        )
        response = self.client.get(third.get_absolute_url())
        self.assertNotContains(response, self.component.get_absolute_url())

        # Can link after gaining management
        third.add_user(self.user, "Administration")
        self.client.post(
            add_url, {"link_add-project": third.pk, "link_add-category": ""}
        )
        response = self.client.get(third.get_absolute_url())
        self.assertContains(response, self.component.get_absolute_url())
