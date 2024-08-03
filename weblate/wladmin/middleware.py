# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import multiprocessing
import time
from random import randint
from threading import Thread
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse

from weblate.accounts.models import AuditLog
from weblate.runner import main

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest

CHECK_CACHE_KEY = "weblate-health-check"


class ManageMiddleware:
    """
    Middleware to trigger periodic management tasks.

    These have to be triggered from the UWSGI context to be able to detect differences
    between Celery and UWSGI environments.
    """

    def __init__(self, get_response=None) -> None:
        self.get_response = get_response

    @staticmethod
    def trigger_check() -> None:
        if not settings.BACKGROUND_ADMIN_CHECKS:
            return
        # Update last execution timestamp
        cache.set(CHECK_CACHE_KEY, time.time())

        # Use safer spawn method
        context = multiprocessing.get_context("spawn")

        # Spawn a management process to do a configuration health check
        # - using threads causes problems with a database connections
        #   (SSL initialization and keeping open persistent connections)
        # - spawning directly the method using multiprocessing is not easy
        #   because of missing invocation of django.setup()
        process = context.Process(
            target=main, kwargs={"argv": ["weblate", "configuration_health_check"]}
        )
        process.start()

        # Make sure we catch SIGCHLD from the spawned process
        thread = Thread(target=process.join)
        thread.start()

    def __call__(self, request: AuthenticatedHttpRequest):
        if request.session.pop("redirect_to_donate", False):
            AuditLog.objects.create(request.user, request, "donate")
            return redirect(reverse("donate"))
        response = self.get_response(request)
        if (
            request.resolver_match
            and request.resolver_match.view_name == "manage-performance"
        ):
            # Always trigger on the performance page
            self.trigger_check()
        elif randint(0, 100) == 1:  # noqa: S311
            # Trigger when last check is too old
            last_run = cache.get(CHECK_CACHE_KEY)
            now = time.time()
            if last_run is None or now - last_run > 900:
                self.trigger_check()

        return response
