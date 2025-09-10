# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for component links."""

from __future__ import annotations

from weblate.trans.models import Project
from weblate.trans.tests.test_views import ViewTestCase


class ComponentLinkTestCase(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.other = Project.objects.create(name="Other", slug="other")
        self.component.links.add(self.other)

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

        def compare_stats(one: dict, other: dict, *, equals: bool = True):
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

        other_component.links.add(third_project)
        third_component.links.add(self.project)

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
