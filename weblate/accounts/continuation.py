# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.signals import user_logged_out
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.serializers.json import DjangoJSONEncoder
from django.dispatch import receiver
from django.http import Http404, QueryDict
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.datastructures import MultiValueDict
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_safe

from weblate.accounts.utils import (
    SESSION_SECOND_FACTOR_CONTINUATION,
    has_recent_sensitive_verification,
    sensitive_verification_redirect,
)
from weblate.utils.lock import LockScope, WeblateLock

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponseBase, HttpResponseRedirect

    from weblate.auth.models import AuthenticatedHttpRequest

LOGGER = logging.getLogger(__name__)

SESSION_PENDING = "weblate:sensitive:pending"
PENDING_TTL = 600
MAX_FORM_BYTES = 256 * 1024


@dataclass(frozen=True)
class Submission:
    data: QueryDict
    query: QueryDict
    files: MultiValueDict | None = None


type Handler = Callable[..., HttpResponseBase]
operations: dict[str, Handler] = {}


def sensitive_operation[H: Handler](name: str) -> Callable[[H], H]:
    """Register an application handler for an explicitly supported operation."""

    def register(handler: H) -> H:
        operations[name] = handler
        return handler

    return register


def _key(token: str) -> str:
    return f"sensitive-submission:{token}"


def _cipher() -> Fernet:
    key = salted_hmac(
        "weblate-sensitive-submission", "encryption", algorithm="sha256"
    ).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def pending_destination(request: HttpRequest, next_url: str) -> bool:
    token = request.session.get(SESSION_PENDING)
    return bool(
        isinstance(token, str)
        and next_url == reverse("pending-sensitive-submission", kwargs={"token": token})
    )


def _resubmit_message(request: HttpRequest) -> None:
    messages.error(
        request,
        gettext("The saved submission could not be completed. Please submit it again."),
    )


def discard_pending_submission(request: HttpRequest) -> None:
    if token := request.session.pop(SESSION_PENDING, None):
        with WeblateLock(scope=LockScope.SENSITIVE_SUBMISSION, key=token):
            cache.delete(_key(token))


@receiver(user_logged_out)
def discard_pending_on_logout(
    sender: object, request: HttpRequest | None, **kwargs: object
) -> None:
    if request is not None:
        try:
            discard_pending_submission(request)
        except Exception:
            LOGGER.warning("Could not clear the pending submission on logout")


@sensitive_post_parameters()
@sensitive_variables()
def stage_sensitive_submission(
    request: AuthenticatedHttpRequest,
    operation: str,
    fallback: str,
    *,
    report_limit: int = 0,
    **target: object,
) -> HttpResponseRedirect:
    """Store input from an authorized browser POST for this verification flow."""
    if request.method != "POST":
        return sensitive_verification_redirect(request, fallback)

    fields = request.POST.copy()
    fields.pop("csrfmiddlewaretoken", None)
    data = fields.urlencode().encode("ascii")
    query = request.GET.urlencode()
    if len(data) + len(query) > MAX_FORM_BYTES:
        _resubmit_message(request)
        return sensitive_verification_redirect(request, fallback)

    report = None
    if request.FILES:
        if report_limit and list(request.FILES) == ["report"]:
            uploads = request.FILES.getlist("report")
            if len(uploads) == 1 and 0 < (uploads[0].size or 0) <= report_limit:
                upload = uploads[0]
                report = (
                    upload.name,
                    upload.content_type,
                    upload.read(report_limit + 1),
                )
        if report is None or len(report[2]) > report_limit:
            _resubmit_message(request)
            return sensitive_verification_redirect(request, fallback)

    header = json.dumps(
        {
            "operation": operation,
            "target": target,
            "fallback": fallback,
            "data": data.decode("ascii"),
            "query": query,
            "user": request.user.pk,
            "hash": request.user.get_session_auth_hash(),
            "report": report[:2] if report is not None else None,
        },
        cls=DjangoJSONEncoder,
    ).encode()
    token = str(uuid4())
    encrypted = _cipher().encrypt(header + b"\n" + (report[2] if report else b""))
    try:
        discard_pending_submission(request)
        if not cache.add(_key(token), encrypted, PENDING_TTL):
            _resubmit_message(request)
            return sensitive_verification_redirect(request, fallback)
    except Exception:
        LOGGER.warning("Could not store the pending submission")
        _resubmit_message(request)
        return sensitive_verification_redirect(request, fallback)

    request.session[SESSION_PENDING] = token
    next_url = reverse("pending-sensitive-submission", kwargs={"token": token})
    return start_pending_verification(request, next_url)


def start_pending_verification(
    request: AuthenticatedHttpRequest, next_url: str
) -> HttpResponseRedirect:
    response = sensitive_verification_redirect(request, next_url)
    if request.user.profile.has_2fa and pending_destination(request, next_url):
        request.session[SESSION_SECOND_FACTOR_CONTINUATION] = request.session[
            SESSION_PENDING
        ]
    return response


def matches_second_factor_continuation(request: HttpRequest, next_url: str) -> bool:
    return (
        request.user.is_authenticated
        and pending_destination(request, next_url)
        and request.session.get(SESSION_SECOND_FACTOR_CONTINUATION)
        == request.session.get(SESSION_PENDING)
    )


@sensitive_variables()
def _claim_pending(
    request: AuthenticatedHttpRequest, token: str
) -> tuple[dict[str, Any], bytes] | None:
    key = _key(token)
    with WeblateLock(scope=LockScope.SENSITIVE_SUBMISSION, key=token):
        encrypted = cache.get(key)
        if not encrypted:
            return None
        payload, _, content = (
            _cipher().decrypt(encrypted, ttl=PENDING_TTL).partition(b"\n")
        )
        pending = json.loads(payload)
        if not (
            request.user.is_authenticated
            and request.user.is_active
            and pending["user"] == request.user.pk
            and constant_time_compare(
                pending["hash"], request.user.get_session_auth_hash()
            )
            and has_recent_sensitive_verification(request)
            and cache.delete(key)
        ):
            return None
        return pending, content


@sensitive_variables()
def complete_sensitive_submission(
    request: AuthenticatedHttpRequest, next_url: str
) -> str:
    """Execute only after a successful credential check for this continuation."""
    if not pending_destination(request, next_url):
        return next_url
    token = request.session.pop(SESSION_PENDING)
    fallback = reverse("profile")
    try:
        claimed = _claim_pending(request, token)
    except InvalidToken:
        claimed = None
    except Exception:
        LOGGER.warning("Could not read the pending submission")
        claimed = None
    if claimed is None:
        _resubmit_message(request)
        return fallback

    pending, content = claimed
    fallback = pending["fallback"]
    files = None
    if pending["report"] is not None:
        name, content_type = pending["report"]

        files = MultiValueDict(
            {"report": [SimpleUploadedFile(name, content, content_type)]}
        )
    submission = Submission(
        QueryDict(pending["data"]), QueryDict(pending["query"]), files
    )
    try:
        response = operations[pending["operation"]](
            request, submission, **pending["target"]
        )
    except (PermissionDenied, Http404):
        _resubmit_message(request)
        return fallback
    except Exception as error:
        LOGGER.warning(
            "Pending submission %s failed (%s)",
            pending["operation"],
            type(error).__name__,
        )
        _resubmit_message(request)
        return fallback
    if 300 <= response.status_code < 400:
        destination = response.headers.get("Location", "")
        if destination.startswith("/") and url_has_allowed_host_and_scheme(
            destination, allowed_hosts={request.get_host()}
        ):
            return destination
    _resubmit_message(request)
    return fallback


@require_safe
@login_required
@never_cache
def pending_submission_fallback(
    request: HttpRequest, token: UUID
) -> HttpResponseRedirect:
    _resubmit_message(request)
    return redirect("profile")
