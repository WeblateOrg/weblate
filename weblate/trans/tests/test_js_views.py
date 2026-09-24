# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for AJAX/JS views."""

from django.test.utils import override_settings
from django.urls import reverse

from weblate.trans.models import Project
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.views.js import MARKDOWN_PREVIEW_MAX_LENGTH


class JSViewsTest(FixtureTestCase):
    """Testing of AJAX/JS views."""

    def test_get_unit_translations(self) -> None:
        unit = self.get_unit()
        response = self.client.get(
            reverse("js-unit-translations", kwargs={"unit_id": unit.id})
        )
        self.assertContains(response, 'href="/translate/')

    def test_markdown_preview(self) -> None:
        response = self.client.post(
            reverse("js-markdown-preview"), {"text": "**bold** @testuser"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="markdown"')
        self.assertContains(response, "<strong>bold</strong>")
        self.assertContains(response, 'href="/user/testuser/"')

    def test_markdown_preview_empty(self) -> None:
        response = self.client.post(reverse("js-markdown-preview"), {"text": "  "})
        self.assertContains(response, "Nothing to preview.")
        self.assertNotContains(response, 'class="markdown"')

    def test_markdown_preview_xss(self) -> None:
        response = self.client.post(
            reverse("js-markdown-preview"), {"text": "<script>alert(1)</script>"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>")

    def test_markdown_preview_get(self) -> None:
        response = self.client.get(reverse("js-markdown-preview"))
        self.assertEqual(response.status_code, 405)

    def test_markdown_preview_anonymous(self) -> None:
        self.client.logout()
        response = self.client.post(reverse("js-markdown-preview"), {"text": "x"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_markdown_preview_too_long(self) -> None:
        response = self.client.post(
            reverse("js-markdown-preview"),
            {"text": "x" * (MARKDOWN_PREVIEW_MAX_LENGTH + 1)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertContains(
            response, "The text is too long to preview.", status_code=400
        )

    @override_settings(RATELIMIT_MARKDOWN_PREVIEW_ATTEMPTS=1)
    def test_markdown_preview_ratelimit(self) -> None:
        url = reverse("js-markdown-preview")
        self.assertEqual(self.client.post(url, {"text": "x"}).status_code, 200)
        response = self.client.post(url, {"text": "x"})
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertContains(response, "Too many preview requests", status_code=429)

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

    def test_get_unit_translations_hides_private_unit(self) -> None:
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save(update_fields=["access_control"])
        self.user.clear_permissions_cache()

        unit = self.get_unit()
        response = self.client.get(
            reverse("js-unit-translations", kwargs={"unit_id": unit.id})
        )
        self.assertEqual(response.status_code, 404)
