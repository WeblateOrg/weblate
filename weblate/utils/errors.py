#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import sys

import sentry_sdk
from django.conf import settings
from django.utils.encoding import force_str
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.integrations.redis import RedisIntegration

import weblate
from weblate.logger import LOGGER

try:
    import rollbar

    HAS_ROLLBAR = True
except ImportError:
    HAS_ROLLBAR = False


def report_error(
    extra_data=None,
    level="warning",
    cause="Handled exception",
    skip_sentry=False,
    print_tb=False,
    logger=None,
):
    """Wrapper for error reporting.

    This can be used for store exceptions in error reporting solutions as rollbar while
    handling error gracefully and giving user cleaner message.
    """
    if logger is None:
        logger = LOGGER
    if HAS_ROLLBAR and hasattr(settings, "ROLLBAR"):
        rollbar.report_exc_info(extra_data=extra_data, level=level)

    if not skip_sentry and settings.SENTRY_DSN:
        with sentry_sdk.push_scope() as scope:
            if extra_data:
                for key, value in extra_data.items():
                    scope.set_extra(key, value)
            scope.set_extra("error_cause", cause)
            scope.level = level
            sentry_sdk.capture_exception()

    log = getattr(logger, level)

    error = sys.exc_info()[1]

    log("%s: %s: %s", cause, error.__class__.__name__, force_str(error))
    if extra_data:
        log("%s: %s: %s", cause, error.__class__.__name__, force_str(extra_data))
    if print_tb:
        logger.exception(cause)


def celery_base_data_hook(request, data):
    data["framework"] = "celery"


def init_error_collection(celery=False):
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[CeleryIntegration(), DjangoIntegration(), RedisIntegration()],
            send_default_pii=True,
            release=weblate.GIT_REVISION or weblate.TAG_NAME,
            environment=settings.SENTRY_ENVIRONMENT,
            **settings.SENTRY_EXTRA_ARGS,
        )
        # Ignore Weblate logging, those should be reported as proper errors
        ignore_logger("weblate")
        ignore_logger("weblate.celery")

    if celery and HAS_ROLLBAR and hasattr(settings, "ROLLBAR"):
        rollbar.init(**settings.ROLLBAR)
        rollbar.BASE_DATA_HOOK = celery_base_data_hook
