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
        """Category stats should include shared components assigned to it."""
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
