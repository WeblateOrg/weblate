# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
from __future__ import unicode_literals

import sentry_sdk
from django.conf import settings
from django.utils.encoding import force_text
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
    error,
    request=None,
    extra_data=None,
    level='warning',
    prefix='Handled exception',
    skip_sentry=False,
    print_tb=False,
    logger=None,
):
    """Wrapper for error reporting

    This can be used for store exceptions in error reporting solutions as
    rollbar while handling error gracefully and giving user cleaner message.
    """
    if logger is None:
        logger = LOGGER
    if HAS_ROLLBAR and hasattr(settings, 'ROLLBAR'):
        rollbar.report_exc_info(request=request, extra_data=extra_data, level=level)

    if not skip_sentry and settings.SENTRY_DSN:
        sentry_sdk.capture_exception()

    logger.error('%s: %s: %s', prefix, error.__class__.__name__, force_text(error))
    if print_tb:
        logger.exception(prefix)


def celery_base_data_hook(request, data):
    data['framework'] = 'celery'


def init_error_collection(celery=False):
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[CeleryIntegration(), DjangoIntegration(), RedisIntegration()],
            send_default_pii=True,
            release=weblate.GIT_REVISION or weblate.VERSION,
        )
        ignore_logger("weblate.celery")

    if celery and HAS_ROLLBAR and hasattr(settings, 'ROLLBAR'):
        rollbar.init(**settings.ROLLBAR)
        rollbar.BASE_DATA_HOOK = celery_base_data_hook
