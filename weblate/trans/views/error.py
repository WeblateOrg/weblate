import logging

from django.conf import settings
from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotFound,
    HttpResponseServerError,
)
from django.middleware.csrf import REASON_NO_CSRF_COOKIE, REASON_NO_REFERER
from django.utils.translation import gettext as _
from rest_framework.exceptions import bad_request as rest_framework_bad_request
from rest_framework.exceptions import server_error as rest_framework_server_error
from sentry_sdk import last_event_id

from weblate.trans.util import render
from weblate.utils.errors import report_error

logger = logging.getLogger(__name__)


def bad_request(request, exception=None):
    """
    Error handler for bad requests.

    Returns an HTTP 400 response for bad requests.
    """
    if not request.accepts("text/html"):
        return rest_framework_bad_request(request, exception)
    if exception:
        report_error(cause="Bad request")
    return render(
        request=request,
        template_name="400.html",
        context={"title": _("Bad Request")},
        status=HttpResponseBadRequest.status_code,
    )


def not_found(request, exception=None):
    """
    Error handler showing list of available projects.

    Returns an HTTP 404 response for not found pages.
    """
    return render(
        request=request,
        template_name="404.html",
        context={"title": _("Page Not Found")},
        status=HttpResponseNotFound.status_code,
    )


def denied(request, exception=None):
    """
    Error handler for permission denied.

    Returns an HTTP 403 response for permission denied.
    """
    return render(
        request=request,
        template_name="403.html",
        context={"title": _("Permission Denied")},
        status=HttpResponseForbidden.status_code,
    )


def csrf_failure(request, reason=""):
    """
    Error handler for CSRF failure.

    Returns an HTTP 403 response for CSRF failure.
    """
    response = render(
        request=request,
        template_name="403_csrf.html",
        context={
            "title": _("Permission Denied"),
            "no_referer": reason == REASON_NO_REFERER,
            "no_cookie": reason == REASON_NO_CSRF_COOKIE,
        },
        status=HttpResponseForbidden.status_code,
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
    """
    Error handler for server errors.

    Returns an HTTP 500 response for server errors.
    """
    if not request.accepts("text/html"):
        return rest_framework_server_error(request)
    try:
        return render(
            request=request,
            template_name="500.html",
            context={
                "title": _("Internal Server Error"),
                "sentry_dsn": settings.SENTRY_DSN,
                "sentry_event_id": last_event_id(),
            },
            status=HttpResponseServerError.status_code,
        )
    except Exception:
        return HttpResponseServerError()
