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

from django.conf import settings
from django.contrib.sites.models import Site

# List of default domain names on which warn user
DEFAULT_DOMAINS = ('example.net', 'example.com')


def get_site_domain():
    """Return current site domain."""
    return Site.objects.get_current().domain


def get_site_url(url=''):
    """Return root url of current site with domain."""
    return '{0}://{1}{2}'.format(
        'https' if settings.ENABLE_HTTPS else 'http',
        get_site_domain(),
        url
    )


def check_domain(domain):
    """Check whether site domain is correctly set"""
    return (
        domain not in DEFAULT_DOMAINS and
        not domain.startswith('http:') and
        not domain.startswith('https:') and
        not domain.endswith('/')
    )
