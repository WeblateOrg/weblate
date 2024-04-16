# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for check views."""

from django.urls import reverse

from weblate.trans.tests.test_views import ViewTestCase


class ChecksViewTest(ViewTestCase):
    """Testing of check views."""

    def test_browse(self) -> None:
        response = self.client.get(reverse("checks"))
        self.assertContains(response, "/same/")

        response = self.client.get(reverse("checks"), kwargs={"path": ("-", "-", "de")})
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse("checks"), kwargs={"path": self.project.get_url_path()}
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse("checks"), kwargs={"path": self.component.get_url_path()}
        )
        self.assertContains(response, "/same/")

    def test_check(self) -> None:
        response = self.client.get(reverse("checks", kwargs={"name": "same"}))
        self.assertContains(response, "/same/")

        response = self.client.get(reverse("checks", kwargs={"name": "ellipsis"}))
        self.assertContains(response, "checks.html#check-ellipsis")

        response = self.client.get(reverse("checks", kwargs={"name": "not-existing"}))
        self.assertEqual(response.status_code, 404)

        response = self.client.get(
            reverse("checks", kwargs={"name": "same"}),
            {"project": self.project.slug},
        )

    def test_project(self) -> None:
        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": self.project.get_url_path()},
            )
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": self.project.get_url_path()},
            ),
            {"lang": "cs"},
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "ellipsis", "path": self.project.get_url_path()},
            )
        )
        self.assertContains(response, "checks.html#check-ellipsis")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "non-existing", "path": self.project.get_url_path()},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_component(self) -> None:
        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "same", "path": self.component.get_url_path()},
            )
        )
        self.assertContains(response, "/same/")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={
                    "name": "multiple_failures",
                    "path": self.component.get_url_path(),
                },
            )
        )
        self.assertContains(response, "/multiple_failures/")

        response = self.client.get(
            reverse(
                "checks",
                kwargs={"name": "non-existing", "path": self.component.get_url_path()},
            )
        )
        self.assertEqual(response.status_code, 404)
