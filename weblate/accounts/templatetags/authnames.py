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
"""Provide user friendly names for social authentication methods."""
from __future__ import unicode_literals
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

SOCIALS = {
    'amazon': {'name': 'Amazon', 'fa_icon': 'amazon'},
    'azuread-oauth2': {'name': 'Azure', 'fa_icon': 'windows'},
    'google': {'name': 'Google', 'fa_icon': 'google'},
    'google-oauth2': {'name': 'Google', 'fa_icon': 'google'},
    'google-plus': {'name': 'Google+', 'fa_icon': 'google-plus'},
    'github': {'name': 'GitHub', 'fa_icon': 'github'},
    'github-enterprise': {'name': 'GitHub Enterprise', 'fa_icon': 'github'},
    'gitlab': {'name': 'GitLab', 'fa_icon': 'gitlab'},
    'bitbucket': {'name': 'Bitbucket', 'fa_icon': 'bitbucket'},
    'bitbucket-oauth2': {'name': 'Bitbucket', 'fa_icon': 'bitbucket'},
    'coinbase': {'name': 'Coinbase', 'fa_icon': 'bitcoin'},
    'email': {'name': 'Email', 'fa_icon': 'at'},
    'opensuse': {'name': 'openSUSE', 'fl_icon': 'opensuse'},
    'ubuntu': {'name': 'Ubuntu', 'fl_icon': 'ubuntu'},
    'fedora': {'name': 'Fedora', 'fl_icon': 'fedora'},
    'facebook': {'name': 'Facebook', 'fa_icon': 'facebook'},
    'twitter': {'name': 'Twitter', 'fa_icon': 'twitter'},
    'stackoverflow': {'name': 'Stack Overflow', 'fa_icon': 'stackoverflow'},
}

FA_SOCIAL_TEMPLATE = '''
<i class="fa fa-lg {extra_class} fa-wl-social fa-{fa_icon}"></i>
{separator}
{name}
'''
FL_SOCIAL_TEMPLATE = '''
<span class="fl fa-lg {extra_class} fl-{fl_icon}"></span>
{separator}
{name}
'''


@register.simple_tag
def auth_name(auth, extra_class='fa-4x', separator='<br />'):
    """Create HTML markup for social authentication method."""

    params = {
        'name': auth,
        'extra_class': extra_class,
        'separator': separator,
        'fa_icon': 'key',
    }

    if auth in SOCIALS:
        params.update(SOCIALS[auth])

    if 'fl_icon' in params:
        html_template = FL_SOCIAL_TEMPLATE
    else:
        html_template = FA_SOCIAL_TEMPLATE

    return mark_safe(html_template.format(**params))


def get_auth_name(auth):
    """Get nice name for authentication backend."""
    if auth in SOCIALS:
        return SOCIALS[auth]['name']
    return auth
