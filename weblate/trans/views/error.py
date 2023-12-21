# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django.views.defaults
import rest_framework.exceptions
from django.conf import settings
from django.middleware.csrf import REASON_NO_CSRF_COOKIE, REASON_NO_REFERER
from django.utils.translation import gettext
from sentry_sdk import last_event_id

from weblate.trans.util import render
from weblate.utils.errors import report_error


def bad_request(request, exception=None):
    """Error handler for bad request."""
    if "text/html" not in request.headers.get("accept", ""):
        return rest_framework.exceptions.bad_request(request, exception)
    if exception:
        report_error(cause="Bad request")
    return render(request, "400.html", {"title": gettext("Bad Request")}, status=400)


def not_found(request, exception=None):
    """Error handler showing list of available projects."""
    return render(request, "404.html", {"title": gettext("Page Not Found")}, status=404)


def denied(request, exception=None):
    return render(
        request, "403.html", {"title": gettext("Permission Denied")}, status=403
    )


def csrf_failure(request, reason=""):
    response = render(
        request,
        "403_csrf.html",
        {
            "title": gettext("Permission Denied"),
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
    # Django 4.0+
    request.META["CSRF_COOKIE_NEEDS_UPDATE"] = False
    return response


def server_error(request):
    """Error handler for server errors."""
    if "text/html" not in request.headers.get("accept", ""):
        return rest_framework.exceptions.server_error(request)
    try:
        return render(
            request,
            "500.html",
            {
                "title": gettext("Internal Server Error"),
                "sentry_dsn": settings.SENTRY_DSN,
                "sentry_event_id": last_event_id(),
            },
            status=500,
        )
    except Exception:
        return django.views.defaults.server_error(request)
