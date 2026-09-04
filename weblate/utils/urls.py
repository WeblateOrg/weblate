# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.urls.resolvers
from django.urls import register_converter
from django.urls.converters import PathConverter, StringConverter

from weblate.trans.defines import CATEGORY_DEPTH

URL_DEPTH = CATEGORY_DEPTH + 3


def get_url_language() -> None:
    """Return the language used to cache URL resolver data."""
    return


def use_language_independent_url_resolver() -> None:
    """Avoid per-language resolver caches for language-independent URLs."""
    # Django uses this module-level function to key its reverse, namespace, and
    # application resolver dictionaries. Weblate does not translate or prefix
    # routes, so using the active language only creates an identical, sizable
    # resolver table for every language. A stable None key lets all languages
    # share one table without changing Django's translation state. The URL tests
    # reject lazy-translated and language-prefixed patterns that would invalidate
    # this assumption.
    django.urls.resolvers.get_language = get_url_language  # type: ignore[attr-defined]


class WeblateSlugConverter(StringConverter):
    regex = "[^/]+"


class GitPathConverter(StringConverter):
    regex = "(info/|git-upload-pack|git-receive-pack)[a-z0-9_/-]*"


class WordConverter(StringConverter):
    regex = "[^/-]+"


class WidgetExtensionConverter(StringConverter):
    regex = "(png|svg)"


class ObjectPathConverter(PathConverter):
    regex = f"[^/]+(/[^/]+){{0,{URL_DEPTH}}}"

    def to_python(self, value):
        return value.split("/")

    def to_url(self, value):
        return "/".join(value)


def register_weblate_converters() -> None:
    register_converter(WeblateSlugConverter, "name")
    register_converter(GitPathConverter, "git_path")
    register_converter(WordConverter, "word")
    register_converter(WidgetExtensionConverter, "extension")
    register_converter(ObjectPathConverter, "object_path")
