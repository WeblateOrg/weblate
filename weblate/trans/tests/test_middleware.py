# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for translation views."""

from __future__ import annotations

from django.contrib.messages import get_messages
from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.db import using_postgresql


class MiddlewareTestCase(FixtureTestCase):
    """Test case insensitive lookups and aliases in middleware."""

    def test_not_found(self) -> None:
        # Non existing fails with 404
        response = self.client.get(reverse("show", kwargs={"path": ["invalid"]}))
        self.assertEqual(response.status_code, 404)

    def test_project_redirect(self) -> None:
        # Different casing should redirect, MySQL always does case insensitive lookups
        if using_postgresql():
            response = self.client.get(
                reverse("show", kwargs={"path": [self.project.slug.upper()]})
            )
            self.assertRedirects(
                response, self.project.get_absolute_url(), status_code=301
            )

    def test_component_redirect(self) -> None:
        # Non existing fails with 404
        kwargs = {"path": [*self.project.get_url_path(), "invalid"]}
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertEqual(response.status_code, 404)

        # Different casing should redirect, MySQL always does case insensitive lookups
        kwargs["path"][-1] = self.component.slug.upper()
        if using_postgresql():
            response = self.client.get(reverse("show", kwargs=kwargs))
            self.assertRedirects(
                response,
                self.component.get_absolute_url(),
                status_code=301,
            )

    def test_translation_redirect(self) -> None:
        # Non existing fails with 404
        kwargs = {"path": [*self.component.get_url_path()]}
        kwargs["path"].append("cs-DE")
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertEqual(response.status_code, 404)

        # Aliased language should redirect
        kwargs["path"][-1] = "czech"
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertRedirects(
            response,
            self.translation.get_absolute_url(),
            status_code=301,
        )

        # Non existing translated language should redirect with an info message
        kwargs["path"][-1] = "Hindi"
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertRedirects(
            response, self.component.get_absolute_url(), status_code=302
        )
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Hindi translation is currently not available", messages[0])

    def test_redirect_category(self) -> None:
        # Non existing category should be omitted
        kwargs = {
            "path": [
                self.project.slug,
                "nonexisting-category",
                self.component.slug,
                self.translation.language.code,
            ]
        }
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertRedirects(
            response,
            self.translation.get_absolute_url(),
            status_code=301,
        )
