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

import time
from random import randint
from threading import Thread

from django.conf import settings
from django.core.cache import cache
from django.core.checks import run_checks

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

    @staticmethod
    def configuration_health_check(checks=None):
        # Run deployment checks if needed
        if checks is None:
            checks = run_checks(include_deployment_checks=True)
        checks_dict = {check.id: check for check in checks}
        criticals = {
            "weblate.E002",
            "weblate.E003",
            "weblate.E007",
            "weblate.E009",
            "weblate.E012",
            "weblate.E013",
            "weblate.E014",
            "weblate.E015",
            "weblate.E017",
            "weblate.E018",
            "weblate.E019",
            "weblate.C023",
            "weblate.C029",
            "weblate.C030",
            "weblate.C031",
            "weblate.C032",
            "weblate.E034",
            "weblate.C035",
            "weblate.C036",
        }
        removals = []
        existing = {error.name: error for error in ConfigurationError.objects.all()}

        for check_id in criticals:
            if check_id in checks_dict:
                check = checks_dict[check_id]
                if check_id in existing:
                    error = existing[check_id]
                    if error.message != check.msg:
                        error.message = check.msg
                        error.save(update_fields=["message"])
                else:
                    ConfigurationError.objects.create(name=check_id, message=check.msg)
            elif check_id in existing:
                removals.append(check_id)

        if removals:
            ConfigurationError.objects.filter(name__in=removals).delete()

    def trigger_check(self):
        if not settings.BACKGROUND_ADMIN_CHECKS:
            return
        # Update last execution timestamp
        cache.set(CHECK_CACHE_KEY, time.time())
        thread = Thread(target=self.configuration_health_check)
        thread.start()

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.resolver_match
            and request.resolver_match.view_name == "manage-performance"
        ):
            # Always trigger on the performance page
            self.trigger_check()
        elif randint(0, 100) == 1:
            # Trigger when last check is too old
            last_run = cache.get(CHECK_CACHE_KEY)
            now = time.time()
            if last_run is None or now - last_run > 900:
                self.trigger_check()

        return response
