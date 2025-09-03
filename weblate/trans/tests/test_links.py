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
        self.project.stats.force_load()
        self.other.stats.force_load()
        self.assertEqual(self.project.stats.all, self.other.stats.all)
        self.maxDiff = None
        self.assertEqual(self.project.stats.get_data(), self.other.stats.get_data())

    def test_stats_edit(self) -> None:
        self.other.stats.force_load()
        start_data = self.other.stats.get_data()

        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

        self.project.stats.force_load()
        self.other.stats.force_load()

        self.maxDiff = None
        self.assertEqual(self.project.stats.get_data(), self.other.stats.get_data())
        self.assertNotEqual(start_data, self.other.stats.get_data())
