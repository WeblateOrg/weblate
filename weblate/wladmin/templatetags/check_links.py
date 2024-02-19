# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import template
from django.utils.html import format_html
from django.utils.translation import gettext

from weblate.utils.checks import check_doc_link

register = template.Library()


@register.simple_tag
def check_link(check):
    fallback = None
    if check.hint and check.hint.startswith("https:"):
        fallback = check.hint
    return configuration_error_link(check.id, fallback=fallback)


@register.simple_tag
def configuration_error_link(check, fallback=None):
    url = check_doc_link(check) or fallback
    if url:
        return format_html(
            '<a class="btn btn-info" href="{}">{}</a>', url, gettext("Documentation")
        )
    return ""
