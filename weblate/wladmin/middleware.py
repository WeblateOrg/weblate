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

from __future__ import unicode_literals

from django.core.cache import cache
from django.core.checks import run_checks
from django.core.exceptions import MiddlewareNotUsed
from django.utils.timezone import now

from weblate.wladmin.models import ConfigurationError


class ConfigurationErrorsMiddleware(object):
    """Middleware that permanently stores startup error messages.

    These can not be directly stored to the database as it
    is not yet available at time these are raised.

    This middleware is active only on first request and then removed
    by raising
    """
    def __init__(self, get_response=None):
        for error in cache.get('configuration-errors', []):
            if 'delete' in error:
                ConfigurationError.objects.remove(error['name'])
            else:
                ConfigurationError.objects.add(
                    error['name'],
                    error['message'],
                    error['timestamp'] if 'timestamp' in error else now(),
                )
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
        raise MiddlewareNotUsed()
