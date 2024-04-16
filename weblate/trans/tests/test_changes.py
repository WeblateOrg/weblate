# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for changes browsing."""

from django.urls import reverse

from weblate.trans.models import Unit
from weblate.trans.tests.test_views import ViewTestCase


class ChangesTest(ViewTestCase):
    def test_basic(self) -> None:
        response = self.client.get(reverse("changes"))
        self.assertContains(response, "Resource update")

    def test_basic_csv_denied(self) -> None:
        response = self.client.get(reverse("changes-csv"))
        self.assertEqual(response.status_code, 403)

    def test_basic_csv(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse("changes-csv"))
        self.assertContains(response, "timestamp,")

    def test_filter(self) -> None:
        response = self.client.get(reverse("changes", kwargs={"path": ["test"]}))
        self.assertContains(response, "Resource update")
        response = self.client.get(
            reverse("changes", kwargs={"path": ["test", "test"]})
        )
        self.assertContains(response, "Resource update")
        response = self.client.get(
            reverse("changes", kwargs={"path": ["test", "test", "cs"]})
        )
        self.assertContains(response, "Resource update")
        response = self.client.get(
            reverse("changes", kwargs={"path": ["-", "-", "cs"]})
        )
        self.assertContains(response, "Resource update")
        response = self.client.get(
            reverse("changes", kwargs={"path": ["testx", "test", "cs"]})
        )
        self.assertEqual(response.status_code, 404)

    def test_string(self) -> None:
        response = self.client.get(
            reverse("changes", kwargs={"path": Unit.objects.all()[0].get_url_path()})
        )
        self.assertContains(response, "Source string added")
        self.assertContains(response, "Changes of string in")

    def test_user(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        response = self.client.get(reverse("changes"), {"user": self.user.username})
        self.assertContains(response, "Translation added")
        self.assertNotContains(response, "Invalid search string!")
