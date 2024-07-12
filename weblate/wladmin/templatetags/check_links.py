# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import template

from weblate.trans.templatetags.translations import render_documentation_icon
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
    return render_documentation_icon(check_doc_link(check) or fallback)
