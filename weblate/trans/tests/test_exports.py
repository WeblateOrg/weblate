# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for data exports."""

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

    def test_data(self) -> None:
        response = self.client.get(reverse("data_project", kwargs=self.kw_project))
        self.assertContains(response, "Test")
