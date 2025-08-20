# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django import template

from weblate.trans.templatetags.translations import render_documentation_icon
from weblate.utils.checks import check_doc_link

if TYPE_CHECKING:
    from django.core.checks import CheckMessage

register = template.Library()


@register.simple_tag
def check_link(check: CheckMessage) -> str:
    fallback = None
    if check.hint and check.hint.startswith("https:"):
        fallback = check.hint
    return configuration_error_link(cast("str", check.id), fallback=fallback)


@register.simple_tag
def configuration_error_link(check: str, fallback: str | None = None) -> str:
    return render_documentation_icon(check_doc_link(check) or fallback)
