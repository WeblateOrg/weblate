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

"""Test for check views."""


from django.urls import reverse

from weblate.trans.tests.test_views import ViewTestCase


class ChecksViewTest(ViewTestCase):
    """Testing of check views."""

    def test_browse(self):
        response = self.client.get(reverse("checks"))
        self.assertContains(response, "/same/")

        response = self.client.get(reverse("checks"), {"lang": "de"})
        self.assertContains(response, "/same/")

        response = self.client.get(reverse("checks"), {"project": self.project.slug})
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse("checks"),
            {"project": self.project.slug, "component": self.component.slug},
        )
        self.assertContains(response, "/same/")

    def test_check(self):
        response = self.client.get(reverse("show_check", kwargs={"name": "same"}))
        self.assertContains(response, "/same/")

        response = self.client.get(reverse("show_check", kwargs={"name": "ellipsis"}))
        self.assertContains(response, "…")

        response = self.client.get(
            reverse("show_check", kwargs={"name": "not-existing"})
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.get(
            reverse("show_check", kwargs={"name": "same"}),
            {"project": self.project.slug},
        )
        self.assertRedirects(
            response,
            reverse(
                "show_check_project",
                kwargs={"name": "same", "project": self.project.slug},
            ),
        )
        response = self.client.get(
            reverse("show_check", kwargs={"name": "same"}), {"lang": "de"}
        )
        self.assertContains(response, "/checks/same/test/?lang=de")

    def test_project(self):
        response = self.client.get(
            reverse(
                "show_check_project",
                kwargs={"name": "same", "project": self.project.slug},
            )
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "show_check_project",
                kwargs={"name": "same", "project": self.project.slug},
            ),
            {"lang": "cs"},
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "show_check_project",
                kwargs={"name": "ellipsis", "project": self.project.slug},
            )
        )
        self.assertContains(response, "…")

        response = self.client.get(
            reverse(
                "show_check_project",
                kwargs={"name": "non-existing", "project": self.project.slug},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_component(self):
        response = self.client.get(
            reverse(
                "show_check_component",
                kwargs={
                    "name": "same",
                    "project": self.project.slug,
                    "component": self.component.slug,
                },
            )
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "show_check_component",
                kwargs={
                    "name": "multiple_failures",
                    "project": self.project.slug,
                    "component": self.component.slug,
                },
            )
        )
        self.assertContains(response, "/multiple_failures/")

        response = self.client.get(
            reverse(
                "show_check_component",
                kwargs={
                    "name": "non-existing",
                    "project": self.project.slug,
                    "component": self.component.slug,
                },
            )
        )
        self.assertEqual(response.status_code, 404)
