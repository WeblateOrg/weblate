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

from django.core.cache import cache
from django.core.checks import run_checks
from django.utils.timezone import now

from weblate.celery import app
from weblate.wladmin.models import ConfigurationError


@app.task
def configuration_health_check(include_deployment_checks=True):
    # Fetch errors from cache, these are created from
    # code executed without apps ready
    for error in cache.get('configuration-errors', []):
        if 'delete' in error:
            ConfigurationError.objects.remove(error['name'])
        else:
            ConfigurationError.objects.add(
                error['name'],
                error['message'],
                error['timestamp'] if 'timestamp' in error else now(),
            )

    # Run deployment checks
    if not include_deployment_checks:
        return
    checks = run_checks(include_deployment_checks=True)
    check_ids = set([check.id for check in checks])
    if 'weblate.E007' in check_ids:
        ConfigurationError.objects.add(
            'Cache',
            'The configured cache backend will lead to serious '
            'performance or consistency issues.'
        )
    else:
        ConfigurationError.objects.remove('Cache')
    if 'weblate.E009' in check_ids:
        ConfigurationError.objects.add(
            'Celery',
            'The Celery tasks queue is too long, either the worker '
            'is not running or is too slow.'
        )
    else:
        ConfigurationError.objects.remove('Celery')


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600,
        configuration_health_check.s(),
        name='configuration-health-check',
    )
