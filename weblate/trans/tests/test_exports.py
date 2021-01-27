#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Tests for data exports."""

import json

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase


class ExportsViewTest(FixtureTestCase):
    def test_view_rss(self):
        response = self.client.get(reverse("rss"))
        self.assertContains(response, "Test/Test")

    def test_view_rss_project(self):
        response = self.client.get(reverse("rss-project", kwargs=self.kw_project))
        self.assertContains(response, "Test/Test")

    def test_view_rss_component(self):
        response = self.client.get(reverse("rss-component", kwargs=self.kw_component))
        self.assertContains(response, "Test/Test")

    def test_view_rss_translation(self):
        response = self.client.get(
            reverse("rss-translation", kwargs=self.kw_translation)
        )
        self.assertContains(response, "Test/Test")

    def test_export_stats(self):
        response = self.client.get(reverse("export_stats", kwargs=self.kw_component))
        parsed = json.loads(response.content.decode())
        self.assertEqual(parsed[0]["name"], "Czech")

    def test_export_stats_csv(self):
        response = self.client.get(
            reverse("export_stats", kwargs=self.kw_component), {"format": "csv"}
        )
        self.assertContains(response, "name,code")

    def test_export_project_stats(self):
        response = self.client.get(reverse("export_stats", kwargs=self.kw_project))
        parsed = json.loads(response.content.decode())
        self.assertIn("Czech", [i["language"] for i in parsed])

    def test_export_project_stats_csv(self):
        response = self.client.get(
            reverse("export_stats", kwargs=self.kw_project), {"format": "csv"}
        )
        self.assertContains(response, "language,code")

    def test_data(self):
        response = self.client.get(reverse("data_project", kwargs=self.kw_project))
        self.assertContains(response, "Test")
