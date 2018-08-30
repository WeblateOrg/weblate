# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import absolute_import, unicode_literals

import logging
import os

from celery import Celery
from celery.signals import task_failure
from celery.schedules import crontab

try:
    import rollbar
    HAS_ROLLBAR = True
except ImportError:
    HAS_ROLLBAR = False

try:
    from raven import Client
    from raven.contrib.celery import register_signal, register_logger_signal
    HAS_RAVEN = True
except ImportError:
    HAS_RAVEN = False


# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weblate.settings')

app = Celery('weblate')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Rollbar integration, based on
# https://www.mattlayman.com/blog/2017/django-celery-rollbar/
if bool(os.environ.get('CELERY_WORKER_RUNNING', False)):
    from django.conf import settings
    if HAS_ROLLBAR and hasattr(settings, 'ROLLBAR'):
        rollbar.init(**settings.ROLLBAR)

        def celery_base_data_hook(request, data):
            data['framework'] = 'celery'

        rollbar.BASE_DATA_HOOK = celery_base_data_hook

        @task_failure.connect
        def handle_task_failure(**kw):
            rollbar.report_exc_info(extra_data=kw)

    if HAS_RAVEN and hasattr(settings, 'RAVEN_CONFIG'):
        client = Client(settings['RAVEN_CONFIG']['dsn'])
        register_signal(client, ignore_expected=True)
        register_logger_signal(client, loglevel=logging.INFO)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    from django.conf import settings
    from weblate.trans.tasks import (
        commit_pending, cleanup_fulltext, optimize_fulltext,
        cleanup_suggestions,
    )
    from weblate.wladmin.tasks import configuration_health_check
    from weblate.screenshots.tasks import cleanup_screenshot_files
    from weblate.accounts.tasks import cleanup_social_auth

    sender.add_periodic_task(
        3600,
        commit_pending.s(),
        name='commit-pending',
    )
    sender.add_periodic_task(
        3600,
        cleanup_social_auth.s(),
        name='social-auth-cleanup',
    )
    sender.add_periodic_task(
        3600 * 24,
        cleanup_screenshot_files.s(),
        name='screenshot-files-cleanup',
    )

    # Following fulltext maintenance tasks should not be
    # executed at same time
    sender.add_periodic_task(
        crontab(hour=2, minute=30, day_of_week='saturday'),
        cleanup_fulltext.s(),
        name='fulltext-cleanup',
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=30, day_of_week='sunday'),
        optimize_fulltext.s(),
        name='fulltext-optimize',
    )

    sender.add_periodic_task(
        3600 * 24,
        cleanup_suggestions.s(),
        name='suggestions-cleanup',
    )
    sender.add_periodic_task(
        3600,
        configuration_health_check.s(),
        name='configuration-health-check',
    )
