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

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from six.moves.urllib.parse import urlparse

from weblate.utils.errors import report_error

CSP_TEMPLATE = (
    "default-src 'self'; style-src {0}; img-src {1}; script-src {2}; "
    "connect-src {3}; object-src 'none'; font-src {4};"
    "frame-src 'none'; frame-ancestors 'none';"
)

# URLs requiring inline javascipt
INLINE_PATHS = {"social:begin"}


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
            address = proxy.split(", ")[settings.IP_PROXY_OFFSET].strip()
            try:
                validate_ipv46_address(address)
                request.META["REMOTE_ADDR"] = address
            except ValidationError as error:
                report_error(error, prefix="Invalid IP address")

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

        style = {"'self'", "'unsafe-inline'"}
        script = {"'self'"}
        image = {"'self'"}
        connect = {"'self'"}
        font = {"'self'"}

        if request.resolver_match and request.resolver_match.view_name in INLINE_PATHS:
            script.add("'unsafe-inline'")

        # Rollbar client errors reporting
        if (
            hasattr(settings, "ROLLBAR")
            and "client_token" in settings.ROLLBAR
            and "environment" in settings.ROLLBAR
            and response.status_code == 500
        ):
            script.add("'unsafe-inline'")
            script.add("cdnjs.cloudflare.com")
            connect.add("api.rollbar.com")

        # Sentry user feedback
        if settings.SENTRY_DSN and response.status_code == 500:
            domain = urlparse(settings.SENTRY_DSN).hostname
            script.add(domain)
            connect.add(domain)
            script.add("'unsafe-inline'")
            image.add("data:")

        # Matomo (Piwik) analytics
        if settings.PIWIK_URL:
            script.add("'unsafe-inline'")
            script.add(settings.PIWIK_URL)
            image.add(settings.PIWIK_URL)
            connect.add(settings.PIWIK_URL)

        # Google Analytics
        if settings.GOOGLE_ANALYTICS_ID:
            script.add("'unsafe-inline'")
            script.add("www.google-analytics.com")
            image.add("www.google-analytics.com")

        # External media URL
        if "://" in settings.MEDIA_URL:
            domain = urlparse(settings.MEDIA_URL).hostname
            image.add(domain)

        # External static URL
        if "://" in settings.STATIC_URL:
            domain = urlparse(settings.STATIC_URL).hostname
            script.add(domain)
            image.add(domain)
            style.add(domain)
            font.add(domain)

        response["Content-Security-Policy"] = CSP_TEMPLATE.format(
            " ".join(style),
            " ".join(image),
            " ".join(script),
            " ".join(connect),
            " ".join(font),
        )
        return response
