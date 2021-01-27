#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import os
from typing import Dict

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

from weblate.utils.errors import report_error

register = template.Library()

CACHE: Dict[str, str] = {}

SPIN = '<span class="icon-spin" {} {}>{}</span>'


@register.simple_tag()
def icon(name):
    """Inlines SVG icon.

    Inlining is necessary to be able to apply CSS styles on the path.
    """
    if not name:
        raise ValueError("Empty icon name")

    if name not in CACHE:
        icon_file = os.path.join(settings.STATIC_ROOT, "icons", name)
        try:
            with open(icon_file) as handle:
                CACHE[name] = mark_safe(handle.read())
        except OSError:
            report_error(cause="Failed to load icon")
            return ""

    return CACHE[name]


@register.simple_tag()
def loading_icon(name=None, hidden=True):
    return mark_safe(
        SPIN.format(
            f'id="loading-{name}"' if name else "",
            'style="display: none"' if hidden else "",
            icon("loading.svg"),
        )
    )
