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

from django.conf import settings
from django.core.mail import get_connection
from django.core.checks import Error

from weblate.utils.celery import get_queue_length
from weblate.utils.docs import get_doc_url

GOOD_CACHE = frozenset((
    'MemcachedCache', 'PyLibMCCache', 'DatabaseCache', 'RedisCache'
))


def check_mail_connection(app_configs, **kwargs):
    errors = []
    try:
        connection = get_connection()
        connection.open()
        connection.close()
    except Exception as error:
        message = 'Can not send email ({}), please check EMAIL_* settings.'
        errors.append(
            Error(
                message.format(error),
                hint=get_doc_url('admin/install', 'out-mail'),
                id='weblate.E003',
            )
        )

    return errors


def check_celery(app_configs, **kwargs):
    errors = []
    if settings.CELERY_TASK_ALWAYS_EAGER:
        errors.append(
            Error(
                'Celery is configured in the eager mode',
                hint=get_doc_url('admin/install', 'celery'),
                id='weblate.E005',
            )
        )

    if get_queue_length() > 1000:
        errors.append(
            Error(
                'Celery tasks queue is too long, is worker running?',
                hint=get_doc_url('admin/install', 'celery'),
                id='weblate.E009',
            )
        )

    return errors


def check_database(app_configs, **kwargs):
    errors = []
    if 'sqlite' in settings.DATABASES['default']['ENGINE']:
        errors.append(
            Error(
                'SQLite is not a good database backend for production use',
                hint=get_doc_url('admin/install', 'production-database'),
                id='weblate.E006',
            )
        )
    return errors


def check_cache(app_configs, **kwargs):
    """Check for sane caching"""
    errors = []

    cache = settings.CACHES['default']['BACKEND'].split('.')[-1]
    if cache not in GOOD_CACHE:
        errors.append(
            Error(
                'Please choose better cache backend such as redis',
                hint=get_doc_url('admin/install', 'production-cache'),
                id='weblate.E007',
            )
        )

    if settings.ENABLE_AVATARS and 'avatar' not in settings.CACHES:
        errors.append(
            Error(
                'Please configure avatar caching',
                hint=get_doc_url('admin/install', 'production-cache-avatar'),
                id='weblate.E008',
            )
        )

    return errors
