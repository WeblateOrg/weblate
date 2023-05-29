# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import register_converter
from django.urls.converters import StringConverter


class WeblateSlugConverter(StringConverter):
    regex = "[^/]+"


class GitPathConverter(StringConverter):
    regex = "(info/|git-upload-pack)[a-z0-9_/-]*"


class WordConverter(StringConverter):
    regex = "[^/-]+"


class WidgetExtensionConverter(StringConverter):
    regex = "(png|svg)"


class OptionalPathConverter(StringConverter):
    regex = "(info/|git-upload-pack)[a-z0-9_/-]*|"


def register_weblate_converters():
    register_converter(WeblateSlugConverter, "name")
    register_converter(GitPathConverter, "gitpath")
    register_converter(WordConverter, "word")
    register_converter(WidgetExtensionConverter, "extension")
    register_converter(OptionalPathConverter, "optionalpath")
