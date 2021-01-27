#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


import django.views.defaults
import rest_framework.exceptions
from django.conf import settings
from django.middleware.csrf import REASON_NO_CSRF_COOKIE, REASON_NO_REFERER
from django.utils.translation import gettext as _
from sentry_sdk import last_event_id

from weblate.trans.util import render
from weblate.utils.errors import report_error


def bad_request(request, exception=None):
    """Error handler for bad request."""
    if "text/html" not in request.META.get("HTTP_ACCEPT", ""):
        return rest_framework.exceptions.bad_request(request, exception)
    if exception:
        report_error(cause="Bad request")
    return render(request, "400.html", {"title": _("Bad Request")}, status=400)


def not_found(request, exception=None):
    """Error handler showing list of available projects."""
    return render(request, "404.html", {"title": _("Page Not Found")}, status=404)


def denied(request, exception=None):
    return render(request, "403.html", {"title": _("Permission Denied")}, status=403)


def csrf_failure(request, reason=""):
    response = render(
        request,
        "403_csrf.html",
        {
            "title": _("Permission Denied"),
            "no_referer": reason == REASON_NO_REFERER,
            "no_cookie": reason == REASON_NO_CSRF_COOKIE,
        },
        status=403,
    )
    # Avoid setting CSRF cookie on CSRF failure page, otherwise we end up creating
    # new session even when user might already have one (because browser did not
    # send the cookies with the CSRF request and Django doesn't see the session
    # cookie).
    response.csrf_cookie_set = True
    return response


def server_error(request):
    """Error handler for server errors."""
    if "text/html" not in request.META.get("HTTP_ACCEPT", ""):
        return rest_framework.exceptions.server_error(request)
    try:
        return render(
            request,
            "500.html",
            {
                "title": _("Internal Server Error"),
                "sentry_dsn": settings.SENTRY_DSN,
                "sentry_event_id": last_event_id(),
            },
            status=500,
        )
    except Exception:
        return django.views.defaults.server_error(request)
