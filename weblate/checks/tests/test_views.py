# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
                "show_check_path",
                kwargs={"name": "same", "path": self.project.get_url_path()},
            ),
        )
        response = self.client.get(
            reverse("show_check", kwargs={"name": "same"}), {"lang": "de"}
        )
        self.assertContains(response, "/checks/same/test/?lang=de")

    def test_project(self):
        response = self.client.get(
            reverse(
                "show_check_path",
                kwargs={"name": "same", "path": self.project.get_url_path()},
            )
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "show_check_path",
                kwargs={"name": "same", "path": self.project.get_url_path()},
            ),
            {"lang": "cs"},
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "show_check_path",
                kwargs={"name": "ellipsis", "path": self.project.get_url_path()},
            )
        )
        self.assertContains(response, "…")

        response = self.client.get(
            reverse(
                "show_check_path",
                kwargs={"name": "non-existing", "path": self.project.get_url_path()},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_component(self):
        response = self.client.get(
            reverse(
                "show_check_path",
                kwargs={"name": "same", "path": self.component.get_url_path()},
            )
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "show_check_path",
                kwargs={
                    "name": "multiple_failures",
                    "path": self.component.get_url_path(),
                },
            )
        )
        self.assertContains(response, "/multiple_failures/")

        response = self.client.get(
            reverse(
                "show_check_path",
                kwargs={"name": "non-existing", "path": self.component.get_url_path()},
            )
        )
        self.assertEqual(response.status_code, 404)
