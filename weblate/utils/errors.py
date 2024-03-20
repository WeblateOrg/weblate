# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import sys
from json import JSONDecodeError

import sentry_sdk
from django.conf import settings
from django.utils.translation import get_language
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.integrations.redis import RedisIntegration

import weblate.utils.version

ERROR_LOGGER = "weblate.errors"
LOGGER = logging.getLogger(ERROR_LOGGER)

try:
    import rollbar

    HAS_ROLLBAR = True
except ImportError:
    HAS_ROLLBAR = False


def report_error(
    level: str = "warning",
    cause: str = "Handled exception",
    *,
    skip_sentry: bool = False,
    print_tb: bool = False,
    extra_log: str | None = None,
    project=None,
    message: bool = False,
):
    """
    Report errors.

    This can be used for store exceptions in error reporting solutions as rollbar while
    handling error gracefully and giving user cleaner message.
    """
    __traceback_hide__ = True  # noqa: F841
    if HAS_ROLLBAR and hasattr(settings, "ROLLBAR"):
        rollbar.report_exc_info(level=level)

    if not skip_sentry and settings.SENTRY_DSN:
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("cause", cause)
            if project is not None:
                scope.set_tag("project", project.slug)
            scope.set_tag("user.locale", get_language())
            scope.level = level
            if message:
                sentry_sdk.capture_message(cause)
            else:
                sentry_sdk.capture_exception()

    log = getattr(LOGGER, level)

    error = sys.exc_info()[1]

    # Include JSON document if available. It might be missing
    # when the error is raised from requests.
    if isinstance(error, JSONDecodeError) and not extra_log and hasattr(error, "doc"):
        extra_log = repr(error.doc)

    if error:
        log("%s: %s: %s", cause, error.__class__.__name__, error)
    if extra_log:
        if error:
            log("%s: %s: %s", cause, error.__class__.__name__, extra_log)
        else:
            log("%s: %s", cause, extra_log)
    if print_tb:
        LOGGER.exception(cause)


def add_breadcrumb(category: str, message: str, level: str = "info", **data):
    # Add breadcrumb only if settings are already loaded,
    # we do not want to force loading settings early
    if not settings.configured or not getattr(settings, "SENTRY_DSN", None):
        return
    sentry_sdk.add_breadcrumb(
        category=category, message=message, level=level, data=data
    )


def celery_base_data_hook(request, data):
    data["framework"] = "celery"


def init_error_collection(celery=False):
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[
                CeleryIntegration(),
                DjangoIntegration(),
                RedisIntegration(),
            ],
            send_default_pii=settings.SENTRY_SEND_PII,
            release=weblate.utils.version.GIT_REVISION
            or weblate.utils.version.TAG_NAME,
            environment=settings.SENTRY_ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
            in_app_include=[
                "weblate",
                "wlhosted",
                "wllegal",
                "weblate_fedora_messaging",
                "weblate_language_data",
                "translate",
            ],
            attach_stacktrace=True,
            _experiments={"max_spans": 2000},
            **settings.SENTRY_EXTRA_ARGS,
        )
        # Ignore Weblate logging, those are reported using capture_exception
        ignore_logger(ERROR_LOGGER)

    if celery and HAS_ROLLBAR and hasattr(settings, "ROLLBAR"):
        rollbar.init(**settings.ROLLBAR)
        rollbar.BASE_DATA_HOOK = celery_base_data_hook
        LOGGER.info("configured Rollbar error collection")
