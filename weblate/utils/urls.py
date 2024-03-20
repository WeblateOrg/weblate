# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import register_converter
from django.urls.converters import PathConverter, StringConverter

from weblate.trans.defines import CATEGORY_DEPTH

URL_DEPTH = CATEGORY_DEPTH + 3


class WeblateSlugConverter(StringConverter):
    regex = "[^/]+"


class GitPathConverter(StringConverter):
    regex = "(info/|git-upload-pack)[a-z0-9_/-]*"


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
