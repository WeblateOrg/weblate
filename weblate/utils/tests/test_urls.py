# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

import django.urls.resolvers
from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.urls.resolvers import LocalePrefixPattern, RegexPattern, RoutePattern
from django.utils.translation import override

from weblate.utils.urls import get_url_language

if TYPE_CHECKING:
    from collections.abc import Iterator


def iter_url_patterns(
    patterns: list[URLPattern | URLResolver],
) -> Iterator[URLPattern | URLResolver]:
    for pattern in patterns:
        yield pattern
        if isinstance(pattern, URLResolver):
            yield from iter_url_patterns(pattern.url_patterns)


class LanguageIndependentURLTest(SimpleTestCase):
    def test_shared_resolver_cache(self) -> None:
        resolver = get_resolver()

        with override("en"):
            english_urls = (reverse("home"), reverse("admin:index"))
            english_caches = (
                resolver.reverse_dict,
                resolver.namespace_dict,
                resolver.app_dict,
            )

        with override("cs"):
            czech_urls = (reverse("home"), reverse("admin:index"))
            czech_caches = (
                resolver.reverse_dict,
                resolver.namespace_dict,
                resolver.app_dict,
            )

        self.assertEqual(english_urls, czech_urls)
        for english_cache, czech_cache in zip(
            english_caches, czech_caches, strict=True
        ):
            self.assertIs(english_cache, czech_cache)

        self.assertIs(
            django.urls.resolvers.get_language,  # type: ignore[attr-defined]
            get_url_language,
        )
        # ruff: ignore[private-member-access]
        self.assertEqual(set(resolver._reverse_dict), {None})
        # ruff: ignore[private-member-access]
        self.assertEqual(
            set(resolver._namespace_dict),  # type: ignore[attr-defined]
            {None},
        )
        # ruff: ignore[private-member-access]
        self.assertEqual(set(resolver._app_dict), {None})  # type: ignore[attr-defined]

    def test_patterns_are_language_independent(self) -> None:
        for url_pattern in iter_url_patterns(get_resolver().url_patterns):
            pattern = url_pattern.pattern
            with self.subTest(pattern=pattern):
                self.assertNotIsInstance(pattern, LocalePrefixPattern)
                if isinstance(pattern, RoutePattern):
                    # ruff: ignore[private-member-access]
                    source = pattern._route  # type: ignore[attr-defined]
                elif isinstance(pattern, RegexPattern):
                    # ruff: ignore[private-member-access]
                    source = pattern._regex  # type: ignore[attr-defined]
                else:
                    self.fail(f"Unsupported URL pattern type: {type(pattern)!r}")
                self.assertIsInstance(source, str)
