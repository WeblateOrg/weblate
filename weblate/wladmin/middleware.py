# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import time
from random import randint
from threading import Thread

from django.conf import settings
from django.core.cache import cache

from weblate.wladmin.models import ConfigurationError

CHECK_CACHE_KEY = "weblate-health-check"


class ManageMiddleware:
    """
    Middleware to trigger periodic management tasks.

    These have to be triggered from the UWSGI context to be able to detect differences
    between Celery and UWSGI environments.
    """

    def __init__(self, get_response=None):
        self.get_response = get_response

    def trigger_check(self):
        if not settings.BACKGROUND_ADMIN_CHECKS:
            return
        # Update last execution timestamp
        cache.set(CHECK_CACHE_KEY, time.time())
        thread = Thread(target=ConfigurationError.objects.configuration_health_check)
        thread.start()

    def __call__(self, request):
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
