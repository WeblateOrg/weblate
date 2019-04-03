# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from random import choice

from django import template
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

register = template.Library()

DONATE = 'https://weblate.org/donate/'
WEBLATE = 'https://weblate.org/'
HTML_CHOICES = (
    (_('Support Weblate'), DONATE),
    (_('More information about Weblate'), WEBLATE),
)


@register.simple_tag
def get_advertisement_link():
    """Return advertisement text."""
    text, url = choice(HTML_CHOICES)
    return mark_safe(
        '<a href="{0}">{1}</a>'.format(
            url, text
        )
    )
