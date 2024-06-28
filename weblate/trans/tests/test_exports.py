# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for data exports."""

import json

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase


class ExportsViewTest(FixtureTestCase):
    def test_view_rss(self) -> None:
        response = self.client.get(reverse("rss"))
        self.assertContains(response, "Test/Test")

    def test_view_rss_project(self) -> None:
        response = self.client.get(
            reverse("rss", kwargs={"path": self.project.get_url_path()})
        )
        self.assertContains(response, "Test/Test")

    def test_view_rss_component(self) -> None:
        response = self.client.get(reverse("rss", kwargs=self.kw_component))
        self.assertContains(response, "Test/Test")

    def test_view_rss_translation(self) -> None:
        response = self.client.get(reverse("rss", kwargs=self.kw_translation))
        self.assertContains(response, "Test/Test")

    def test_export_stats(self) -> None:
        response = self.client.get(reverse("export_stats", kwargs=self.kw_component))
        parsed = json.loads(response.content.decode())
        self.assertEqual(parsed[0]["name"], "Czech")

    def test_export_stats_csv(self) -> None:
        response = self.client.get(
            reverse("export_stats", kwargs=self.kw_component),
            {"format": "csv"},
        )
        self.assertContains(response, "name,code")

    def test_export_project_stats(self) -> None:
        response = self.client.get(
            reverse("export_stats", kwargs={"path": self.project.get_url_path()})
        )
        parsed = json.loads(response.content.decode())
        self.assertIn("Czech", [i["name"] for i in parsed])

    def test_export_project_stats_csv(self) -> None:
        response = self.client.get(
            reverse("export_stats", kwargs={"path": self.project.get_url_path()}),
            {"format": "csv"},
        )
        self.assertContains(response, "name,code")

    def test_data(self) -> None:
        response = self.client.get(reverse("data_project", kwargs=self.kw_project))
        self.assertContains(response, "Test")
