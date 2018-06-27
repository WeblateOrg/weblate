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

from six.moves.urllib.parse import urlparse

from django.conf import settings


CSP_TEMPLATE = (
    "default-src 'self'; style-src {0}; img-src {1}; script-src {2}; "
    "connect-src {3}; object-src 'none'; font-src {4};"
    "child-src 'none'; frame-ancestors 'none';"
)


class SecurityMiddleware(object):
    """Middleware that sets Content-Security-Policy"""
    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # No CSP for debug mode (to allow djdt or error pages)
        if settings.DEBUG:
            return response

        style = set(["'self'", "'unsafe-inline'"])
        script = set(["'self'"])
        image = set(["'self'"])
        connect = set(["'self'"])
        font = set(["'self'"])

        if (hasattr(settings, 'ROLLBAR') and
                'client_token' in settings.ROLLBAR and
                'environment' in settings.ROLLBAR):
            script.add("'unsafe-inline'")
            script.add('cdnjs.cloudflare.com')
            connect.add('api.rollbar.com')

        if settings.PIWIK_URL:
            script.add("'unsafe-inline'")
            script.add(settings.PIWIK_URL)
            image.add(settings.PIWIK_URL)

        if settings.GOOGLE_ANALYTICS_ID:
            script.add("'unsafe-inline'")
            script.add('www.google-analytics.com')
            image.add('www.google-analytics.com')

        if '://' in settings.MEDIA_URL:
            domain = urlparse(settings.MEDIA_URL).netloc
            image.add(domain)

        if '://' in settings.STATIC_URL:
            domain = urlparse(settings.STATIC_URL).netloc
            script.add(domain)
            image.add(domain)
            style.add(domain)
            font.add(domain)

        response['Content-Security-Policy'] = CSP_TEMPLATE.format(
            ' '.join(style),
            ' '.join(image),
            ' '.join(script),
            ' '.join(connect),
            ' '.join(font),
        )
        return response
