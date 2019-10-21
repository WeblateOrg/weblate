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

from __future__ import absolute_import, unicode_literals

import logging
import os

from celery import Celery
from celery.signals import task_failure

LOGGER = logging.getLogger('weblate.celery')

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


@task_failure.connect
def handle_task_failure(exception=None, **kwargs):
    from weblate.utils.errors import report_error

    report_error(
        exception,
        extra_data=kwargs,
        prefix='Failure while executing task',
        skip_sentry=True,
        print_tb=True,
        logger=LOGGER,
    )


@app.on_after_configure.connect
def configure_error_handling(sender, **kargs):
    """Rollbar and Sentry integration

    Based on
    https://www.mattlayman.com/blog/2017/django-celery-rollbar/
    """
    if not bool(os.environ.get('CELERY_WORKER_RUNNING', False)):
        return

    from weblate.utils.errors import init_error_collection

    init_error_collection(celery=True)
