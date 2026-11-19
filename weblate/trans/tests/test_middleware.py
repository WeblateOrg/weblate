# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for translation views."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.db import connection
from django.http import HttpResponse
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from weblate.middleware import RedirectMiddleware
from weblate.trans.models import Category
from weblate.trans.models.component import Component, ComponentQuerySet
from weblate.trans.tests.test_views import FixtureTestCase


class MiddlewareTestCase(FixtureTestCase):
    """Test case insensitive lookups and aliases in middleware."""

    def test_existing_translations_check_avoids_language_listing(self) -> None:
        middleware = RedirectMiddleware(lambda _request: HttpResponse())
        language = self.translation.language

        with CaptureQueriesContext(connection) as queries:
            self.assertTrue(
                middleware.check_existing_translations(language, self.project)
            )

        sql = " ".join(query["sql"] for query in queries)
        self.assertNotIn("lang_language", sql)

    def test_not_found(self) -> None:
        # Non existing fails with 404
        response = self.client.get(reverse("show", kwargs={"path": ["invalid"]}))
        self.assertEqual(response.status_code, 404)

    def test_project_redirect(self) -> None:
        # Different casing should redirect
        response = self.client.get(
            reverse("show", kwargs={"path": [self.project.slug.upper()]})
        )
        self.assertRedirects(response, self.project.get_absolute_url(), status_code=301)

    def test_component_redirect(self) -> None:
        # Non existing fails with 404
        kwargs = {"path": [*self.project.get_url_path(), "invalid"]}
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertEqual(response.status_code, 404)

        # Different casing should redirect
        kwargs["path"][-1] = self.component.slug.upper()
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

    def test_untranslated_project_language_alias_redirects_to_language_page(
        self,
    ) -> None:
        path = [self.project.slug, "-", "Hindi"]
        canonical_path = [self.project.slug, "-", "hi"]
        response = self.client.get(reverse("show", kwargs={"path": path}))
        self.assertRedirects(
            response, reverse("show", kwargs={"path": canonical_path}), status_code=301
        )

    def test_ambiguous_component_redirect_returns_not_found(self) -> None:
        path = [*self.project.get_url_path(), self.component.slug.upper()]
        with patch.object(
            ComponentQuerySet,
            "get",
            side_effect=Component.MultipleObjectsReturned,
        ):
            response = self.client.get(reverse("show", kwargs={"path": path}))
        self.assertEqual(response.status_code, 404)

    def test_component_redirect_reuses_lookup_and_normalizes_language(self) -> None:
        path = [self.project.slug, self.component.slug.upper(), "czech"]
        with (
            patch.object(RedirectMiddleware, "fixup_component") as fixup,
            CaptureQueriesContext(connection) as queries,
        ):
            response = self.client.get(f"{reverse('show', kwargs={'path': path})}?a=b")
        fixup.assert_not_called()
        self.assertEqual(
            sum('UPPER("trans_component"."slug"' in query["sql"] for query in queries),
            1,
        )
        self.assertRedirects(
            response,
            f"{self.translation.get_absolute_url()}?a=b",
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_component_case_redirect_respects_restricted_access(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(restricted=True)
        path = [self.project.slug, self.component.slug.upper()]
        response = self.client.get(reverse("show", kwargs={"path": path}))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("Location", response)

    def test_exact_category_wins_over_component_with_different_case(self) -> None:
        category = Category.objects.create(
            project=self.project, name="Category", slug=self.component.slug.upper()
        )
        response = self.client.get(category.get_absolute_url())
        self.assertEqual(response.status_code, 200)

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
