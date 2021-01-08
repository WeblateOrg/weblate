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

"""Tests for changes browsing."""

from django.urls import reverse

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
        self.assertNotContains(response, "Failed to find matching project!")
        response = self.client.get(
            reverse("changes"), {"project": "test", "component": "test"}
        )
        self.assertContains(response, "Resource update")
        self.assertNotContains(response, "Failed to find matching project!")
        response = self.client.get(
            reverse("changes"), {"project": "test", "component": "test", "lang": "cs"}
        )
        self.assertContains(response, "Resource update")
        self.assertNotContains(response, "Failed to find matching project!")
        response = self.client.get(reverse("changes"), {"lang": "cs"})
        self.assertContains(response, "Resource update")
        self.assertNotContains(response, "Failed to find matching language!")
        response = self.client.get(
            reverse("changes"), {"project": "testx", "component": "test", "lang": "cs"}
        )
        self.assertContains(response, "Resource update")
        self.assertContains(response, "Failed to find matching project!")
        response = self.client.get(
            reverse("changes"),
            {"project": "test\000x", "component": "test", "lang": "cs"},
        )
        self.assertContains(response, "Resource update")
        self.assertContains(response, "Null characters are not allowed")

    def test_user(self):
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        response = self.client.get(reverse("changes"), {"user": self.user.username})
        self.assertContains(response, "New translation")
        self.assertNotContains(response, "Invalid search string!")
