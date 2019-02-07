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

from six.moves.urllib.parse import urlparse

from django.conf import settings


CSP_TEMPLATE = (
    "default-src 'self'; style-src {0}; img-src {1}; script-src {2}; "
    "connect-src {3}; object-src 'none'; font-src {4};"
    "frame-src 'none'; frame-ancestors 'none';"
)


class ProxyMiddleware(object):
    """Middleware that updates REMOTE_ADDR from proxy

    Note that this can have security implications and settings
    have to match your actual proxy setup."""
    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        proxy = None
        if settings.IP_BEHIND_REVERSE_PROXY:
            proxy = request.META.get(settings.IP_PROXY_HEADER)
        if proxy:
            # X_FORWARDED_FOR returns client1, proxy1, proxy2,...
            address = proxy.split(', ')[settings.IP_PROXY_OFFSET].strip()
            request.META['REMOTE_ADDR'] = address

        return self.get_response(request)


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

        if (hasattr(settings, 'RAVEN_CONFIG') and
                'public_dsn' in settings.RAVEN_CONFIG):
            domain = urlparse(settings.RAVEN_CONFIG['public_dsn']).hostname
            script.add(domain)
            connect.add(domain)
            script.add("'unsafe-inline'")
            script.add('cdn.ravenjs.com')
            image.add('data:')

        if settings.PIWIK_URL:
            script.add("'unsafe-inline'")
            script.add(settings.PIWIK_URL)
            image.add(settings.PIWIK_URL)
            connect.add(settings.PIWIK_URL)

        if settings.GOOGLE_ANALYTICS_ID:
            script.add("'unsafe-inline'")
            script.add('www.google-analytics.com')
            image.add('www.google-analytics.com')

        if '://' in settings.MEDIA_URL:
            domain = urlparse(settings.MEDIA_URL).hostname
            image.add(domain)

        if '://' in settings.STATIC_URL:
            domain = urlparse(settings.STATIC_URL).hostname
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
