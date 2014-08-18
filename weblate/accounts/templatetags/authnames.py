# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Provides user friendly names for social authentication methods.
"""
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape

register = template.Library()

SOCIALS = {
    'google': ('Google', ''),
    'github': ('GitHub', ''),
    'email': ('Email', ''),
    'opensuse': ('openSUSE', ''),
}


@register.simple_tag
def auth_name(auth):
    """
    Creates HTML markup for social authentication method.
    """

    if auth in SOCIALS:
        return mark_safe(
            '{0}{1}'.format(
                SOCIALS[auth][1],
                escape(SOCIALS[auth][0]),
            )
        )

    return auth
