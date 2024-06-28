# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for data exports."""

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase
from weblate.vcs.ssh import ensure_ssh_key


class BasicViewTest(FixtureTestCase):
    def test_about(self) -> None:
        response = self.client.get(reverse("about"))
        self.assertContains(response, "translate-toolkit")

    def test_keys(self) -> None:
        ensure_ssh_key()
        response = self.client.get(reverse("keys"))
        self.assertContains(response, "SSH")

    def test_stats(self) -> None:
        response = self.client.get(reverse("stats"))
        self.assertContains(response, "Weblate statistics")

    def test_donate(self) -> None:
        response = self.client.get(reverse("donate"))
        self.assertContains(response, "Support Weblate")

    def test_healthz(self) -> None:
        response = self.client.get(reverse("healthz"))
        self.assertContains(response, "ok")
