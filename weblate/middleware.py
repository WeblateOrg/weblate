# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

from django.conf import settings


CSP_TEMPLATE = (
    "default-src 'self'; style-src {0}; img-src {1}; script-src {2}; "
    "connect-src 'none'; object-src 'none'; "
    "child-src 'none'; frame-ancestors 'none';"
)


class SecurityMiddleware(object):
    """Middleware that sets various security related headers.

    - Content-Security-Policy
    - X-XSS-Protection
    """
    def process_response(self, request, response):
        # No CSP for debug mode (to allow djdt or error pages)
        if settings.DEBUG:
            return response

        style = ["'self'", "'unsafe-inline'"]
        script = ["'self'"]
        image = ["'self'"]

        if (hasattr(settings, 'ROLLBAR') and
                'client_token' in settings.ROLLBAR and
                'environment' in settings.ROLLBAR):
            script.append("'unsafe-inline'")
            script.append('cdnjs.cloudflare.com')

        if settings.PIWIK_URL:
            script.append(PIWIK_URL)
            image.append(PIWIK_URL)

        if settings.GOOGLE_ANALYTICS_ID:
            script.append('www.google-analytics.com')
            image.append('www.google-analytics.com')

        response['Content-Security-Policy'] = CSP_TEMPLATE.format(
            ' '.join(style),
            ' '.join(image),
            ' '.join(script),
        )
        response['X-XSS-Protection'] = '1; mode=block'
        return response
