# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for AJAX/JS views."""

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase


class JSViewsTest(FixtureTestCase):
    """Testing of AJAX/JS views."""

    def test_get_unit_translations(self) -> None:
        unit = self.get_unit()
        response = self.client.get(
            reverse("js-unit-translations", kwargs={"unit_id": unit.id})
        )
        self.assertContains(response, 'href="/translate/')

    def test_flag_choices(self) -> None:
        response = self.client.get(reverse("js-flag-choices"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIn("choices", data)
        self.assertGreater(len(data["choices"]), 0)
        names = {entry["name"] for entry in data["choices"]}
        self.assertIn("read-only", names)
        self.assertIn("max-length", names)

    def test_flag_choices_language_param(self) -> None:
        # Unknown language is ignored
        response = self.client.get(
            reverse("js-flag-choices"), {"lang": "not-a-real-language"}
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("js-flag-choices"), {"lang": "cs"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("private", response.get("Cache-Control", ""))
