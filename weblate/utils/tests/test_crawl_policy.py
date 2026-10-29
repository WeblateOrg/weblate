# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock

from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import include, path, resolve

from weblate.urls import real_patterns
from weblate.utils.crawl_policy import crawl_allowed, robots


class CrawlPolicyTest(SimpleTestCase):
    def test_robots(self) -> None:
        for prefix in ("", "/hosted"):
            urlconf = (
                (path("hosted/", include(real_patterns)),)
                if prefix
                else tuple(real_patterns)
            )
            with override_settings(URL_PREFIX=prefix, ROOT_URLCONF=urlconf):
                # Calling the view directly must not need application middleware,
                # session state, or database-backed context processors.
                response = robots(RequestFactory().get(prefix + "/robots.txt"))
                body = response.content.decode()
                self.assertEqual(response["Content-Type"], "text/plain")
                self.assertIn(f"Allow: {prefix}/$\n", body)
                self.assertIn(f"Allow: {prefix}/projects/\n", body)
                self.assertIn(f"Allow: {prefix}/sitemap.xml$\n", body)
                self.assertIn(f"{prefix}/sitemap.xml", body.split("Sitemap: ")[1])
                self.assertIn("Disallow: /\n", body)
                self.assertIn("max-age=86400", response["Cache-Control"])
                for rule in body.splitlines():
                    if rule.startswith("Allow: "):
                        example = (
                            rule.removeprefix("Allow: ")
                            .removeprefix(prefix)
                            .removesuffix("$")
                            .replace("*", "project")
                        )
                        self.assertTrue(crawl_allowed(example), example)
        for route in (
            "/search/",
            "/projects-other/",
            "/sitemap.xml/extra",
            "/sitemap-project.xml/extra",
            "/about/",
        ):
            self.assertFalse(crawl_allowed(route), route)

    def test_public_login_exemptions(self) -> None:
        factory = RequestFactory()
        middleware = LoginRequiredMiddleware(lambda _request: HttpResponse())
        for route in (
            "/robots.txt",
            "/favicon.ico",
            "/apple-touch-icon.png",
            "/android-chrome-192x192.png",
            "/favicon-512x512.png",
            "/browserconfig.xml",
            "/site.webmanifest",
            "/css/custom.css",
            "/.well-known/security.txt",
            "/security.txt",
        ):
            request = factory.get(route)
            request.user = Mock(is_authenticated=False)
            match = resolve(route)
            self.assertIsNone(
                middleware.process_view(request, match.func, match.args, match.kwargs),
                route,
            )
