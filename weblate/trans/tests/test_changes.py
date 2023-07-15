# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for changes browsing."""

from django.urls import reverse

from weblate.trans.models import Unit
from weblate.trans.tests.test_views import ViewTestCase


class ChangesTest(ViewTestCase):
    def test_basic(self):
        response = self.client.get(reverse("changes"))
        self.assertContains(response, "Resource update")

    def test_basic_csv_denied(self):
        response = self.client.get(reverse("changes-csv"))
        self.assertEqual(response.status_code, 403)

    def test_basic_csv(self):
        self.make_manager()
        response = self.client.get(reverse("changes-csv"))
        self.assertContains(response, "timestamp,")

    def test_filter(self):
        response = self.client.get(reverse("changes"), {"project": "test"})
        self.assertContains(response, "Resource update")
        self.assertNotContains(response, "Could not find matching project!")
        response = self.client.get(
            reverse("changes"), {"project": "test", "component": "test"}
        )
        self.assertContains(response, "Resource update")
        self.assertNotContains(response, "Could not find matching project!")
        response = self.client.get(
            reverse("changes"), {"project": "test", "component": "test", "lang": "cs"}
        )
        self.assertContains(response, "Resource update")
        self.assertNotContains(response, "Could not find matching project!")
        response = self.client.get(reverse("changes"), {"lang": "cs"})
        self.assertContains(response, "Resource update")
        self.assertNotContains(response, "Could not find matching language!")
        response = self.client.get(
            reverse("changes"), {"project": "testx", "component": "test", "lang": "cs"}
        )
        self.assertContains(response, "Resource update")
        self.assertContains(response, "Could not find matching project!")
        response = self.client.get(
            reverse("changes"),
            {"project": "\000testx", "component": "test", "lang": "cs"},
        )
        self.assertContains(response, "Resource update")
        self.assertContains(response, "testx is not one of the available choices")

    def test_string(self):
        response = self.client.get(
            reverse("changes"), {"string": Unit.objects.first().pk}
        )
        self.assertContains(response, "New source string")
        self.assertContains(response, "Changes of string in")

    def test_user(self):
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        response = self.client.get(reverse("changes"), {"user": self.user.username})
        self.assertContains(response, "New translation")
        self.assertNotContains(response, "Invalid search string!")
