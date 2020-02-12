# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import os

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

from weblate.logger import LOGGER
from weblate.utils.errors import report_error

register = template.Library()

CACHE = {}

SPIN = '<span class="icon-spin" {} {}>{}</span>'


@register.simple_tag()
def icon(name, fallback=None):
    if fallback is not None:
        name = fallback

    if not name:
        LOGGER.error("Empty icon name")
        return ""

    if name not in CACHE:
        icon_file = os.path.join(settings.STATIC_ROOT, "icons", name)
        try:
            with open(icon_file, "r") as handle:
                CACHE[name] = mark_safe(handle.read())
        except OSError as error:
            report_error(error, prefix="Failed to load icon")
            return ""

    return CACHE[name]


@register.simple_tag()
def loading_icon(name=None, hidden=True):
    return mark_safe(
        SPIN.format(
            'id="loading-{}"'.format(name) if name else '',
            'style="display: none"' if hidden else '',
            icon('loading.svg')
        )
    )
