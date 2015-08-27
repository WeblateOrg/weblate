# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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

register = template.Library()

SOCIALS = {
    'amazon': {'name': 'Amazon', 'fa_icon': 'amazon'},
    'google': {'name': 'Google', 'fa_icon': 'google'},
    'google-oauth2': {'name': 'Google', 'fa_icon': 'google'},
    'google-plus': {'name': 'Google+', 'fa_icon': 'google-plus'},
    'github': {'name': 'GitHub', 'fa_icon': 'github'},
    'github-enterprise': {'name': 'GitHub Enterprise', 'fa_icon': 'github'},
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

FA_SOCIAL_TEMPLATE = u'<i class="fa fa-lg fa-4x fa-wl-social fa-{fa_icon}"></i><br />{name}'
FL_SOCIAL_TEMPLATE = u'<span class="fl fa-lg fa-4x fl-{fl_icon}"></span><br />{name}'


@register.simple_tag
def auth_name(auth):
    """
    Creates HTML markup for social authentication method.
    """

    if auth in SOCIALS:
        auth_data = SOCIALS[auth]
        if 'fa_icon' in auth_data:
            return mark_safe(FA_SOCIAL_TEMPLATE.format(**auth_data))
        elif 'fl_icon' in auth_data:
            return mark_safe(FL_SOCIAL_TEMPLATE.format(**auth_data))

        auth = auth_data['name']

    return mark_safe(FA_SOCIAL_TEMPLATE.format(
        fa_icon='key',
        name=auth,
    ))
