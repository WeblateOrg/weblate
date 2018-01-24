# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
BOUNTYSOURCE = 'https://salt.bountysource.com/teams/weblate'
LIBERAPAY = 'https://liberapay.com/Weblate/donate'
WEBLATE = 'https://weblate.org/'
TEXT_CHOICES = (
    (_('Donate to Weblate at {0}'), DONATE),
    (_('Support Weblate at {0}'), LIBERAPAY),
    (_('Support Weblate at {0}'), BOUNTYSOURCE),
    (_('More information about Weblate can be found at {0}'), WEBLATE),
)
HTML_CHOICES = (
    (_('Donate to Weblate'), DONATE),
    (_('Support Weblate on Liberapay'), LIBERAPAY),
    (_('Support Weblate on Bountysource'), BOUNTYSOURCE),
    (_('More information about Weblate'), WEBLATE),
)


@register.simple_tag
def get_advertisement_text_mail():
    """Return advertisement text."""
    text, url = choice(TEXT_CHOICES)
    return text.format(url)


@register.simple_tag
def get_advertisement_html_mail():
    """Return advertisement text."""
    text, url = choice(HTML_CHOICES)
    return mark_safe(
        '<a href="{0}">{1}</a>'.format(
            url, text
        )
    )
