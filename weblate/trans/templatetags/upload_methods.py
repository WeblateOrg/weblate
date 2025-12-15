# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django import template
from django.utils.translation import gettext

if TYPE_CHECKING:
    from weblate.utils.files import FileUploadMethod


register = template.Library()


@register.simple_tag
def get_upload_method_help(method: str | FileUploadMethod) -> str:
    match method:
        case "translate":
            return gettext(
                "Imported strings are added as translations to existing strings. This is the most common usecase, and the default behavior."
            )
        case "approve":
            return gettext(
                "Imported strings are added as approved translations. Do this when you already reviewed your translations before uploading them."
            )
        case "suggest":
            return gettext(
                "Imported strings are added as suggestions. Do this when you want to have your uploaded strings reviewed."
            )
        case "fuzzy":
            return gettext(
                "Imported strings are added as translations needing edit. This can be useful when you want translations to be used, but also reviewed."
            )
        case "replace":
            return gettext(
                "Existing file is replaced with new content. This can lead to loss of existing translations, use with caution."
            )
        case "add":
            return gettext(
                "Adds new strings to the translation. It skips the ones which already exist."
            )
        case "source":
            return gettext("Updates source strings in bilingual translation file.")

    msg = f"Invalid method: {method!r}"
    raise ValueError(msg)
