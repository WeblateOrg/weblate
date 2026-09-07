# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json

from django.utils.formats import number_format as django_number_format
from django.utils.html import format_html, linebreaks
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from weblate.utils.templatetags.icons import icon


def format_json(value: dict) -> str:
    return mark_safe(linebreaks(json.dumps(value, indent=4), autoescape=True))  # ruff: ignore[suspicious-mark-safe-usage]


def number_format(number: int) -> str:
    format_string = "%s"
    if number > 99999999:
        number //= 1000000
        # Translators: Number format, in millions (mega)
        format_string = gettext("%s M")
    elif number > 99999:
        number //= 1000
        # Translators: Number format, in thousands (kilo)
        format_string = gettext("%s k")
    return format_string % django_number_format(number, force_grouping=True)


def render_documentation_icon(doc_url: str, *, right: bool = False):
    if not doc_url:
        return ""
    return format_html(
        """<a class="{} doc-link" href="{}" title="{}" target="_blank" rel="noopener">{}</a>""",
        "float-end" if right else "",
        doc_url,
        gettext("Documentation"),
        icon("info.svg"),
    )
