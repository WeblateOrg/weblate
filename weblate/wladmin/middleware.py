# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time
from threading import Lock, Thread
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

from weblate.accounts.models import AuditLog
from weblate.utils.errors import report_error
from weblate.wladmin.models import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.core.checks import CheckMessage
    from django.http import HttpResponse

    from weblate.auth.models import AuthenticatedHttpRequest

CHECK_CACHE_KEY = "weblate-health-check"
CHECK_ATTEMPT_CACHE_KEY = f"{CHECK_CACHE_KEY}-attempt"
CHECK_INTERVAL = 3600
CHECK_ATTEMPT_TIMEOUT = 300
CHECK_POLL_INTERVAL = 60


def claim_configuration_health_check() -> bool:
    """Atomically claim a health-check attempt across web workers."""
    return cache.add(
        CHECK_ATTEMPT_CACHE_KEY,
        time.time(),
        timeout=CHECK_ATTEMPT_TIMEOUT,
    )


def perform_configuration_health_check(
    checks: Iterable[CheckMessage] | None = None,
) -> bool:
    """Run and persist a configuration health check."""
    try:
        ConfigurationError.objects.configuration_health_check(checks)
        cache.set(CHECK_CACHE_KEY, time.time(), timeout=None)
    except Exception:
        report_error("Configuration health check failed")
        return False
    return True


def run_background_configuration_health_check() -> None:
    """Run a health check and close connections owned by this thread."""
    try:
        perform_configuration_health_check()
    finally:
        connections.close_all()


class ManageMiddleware(MiddlewareMixin):
    """
    Middleware to trigger periodic management tasks.

    These have to run in the website process to detect differences between the
    Celery and website environments.
    """

    def __init__(self, get_response) -> None:
        super().__init__(get_response)
        self._poll_lock = Lock()
        self._next_poll = 0.0

    def should_poll(self) -> bool:
        """Limit shared-cache polling in each web process."""
        with self._poll_lock:
            now = time.monotonic()
            if now < self._next_poll:
                return False
            self._next_poll = now + CHECK_POLL_INTERVAL
        return True

    @staticmethod
    def trigger_check() -> None:
        if not settings.BACKGROUND_ADMIN_CHECKS:
            return
        if not claim_configuration_health_check():
            return

        try:
            thread = Thread(
                target=run_background_configuration_health_check,
                name="configuration-health-check",
                daemon=False,
            )
            thread.start()
        except Exception:
            report_error("Could not start configuration health check")

    def trigger_check_if_due(self) -> None:
        if not settings.BACKGROUND_ADMIN_CHECKS or not self.should_poll():
            return
        last_success = cache.get(CHECK_CACHE_KEY)
        if last_success is None or time.time() - last_success >= CHECK_INTERVAL:
            self.trigger_check()

    def process_request(self, request: AuthenticatedHttpRequest):
        if request.session.pop("redirect_to_donate", False):
            AuditLog.objects.create(request.user, request, "donate")
            request.__dict__["_skip_configuration_health_check"] = True
            return redirect(reverse("donate"))
        return None

    def process_response(
        self, request: AuthenticatedHttpRequest, response: HttpResponse
    ) -> HttpResponse:
        if not request.__dict__.pop("_skip_configuration_health_check", False):
            self.trigger_check_if_due()
        return response
