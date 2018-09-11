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

import os.path

from django.conf import settings
from django.core.mail import get_connection
from django.core.checks import Error, Critical

import six

from weblate import settings_example
from weblate.utils.celery import get_queue_length
from weblate.utils.data import data_dir
from weblate.utils.docs import get_doc_url

GOOD_CACHE = frozenset((
    'MemcachedCache', 'PyLibMCCache', 'DatabaseCache', 'RedisCache'
))
DEFAULT_MAILS = frozenset((
    'root@localhost',
    'webmaster@localhost',
    'noreply@weblate.org',
    'noreply@example.com'
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
            Critical(
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
            Critical(
                'The Celery tasks queue is too long, either the worker '
-               'is not running or is too slow.',
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
            Critical(
                'The configured cache backend will lead to serious '
                'performance or consistency issues.',
                hint=get_doc_url('admin/install', 'production-cache'),
                id='weblate.E007',
            )
        )

    if settings.ENABLE_AVATARS and 'avatar' not in settings.CACHES:
        errors.append(
            Error(
                'Please configure separate avatar caching to reduce pressure '
                'on the default cache',
                hint=get_doc_url('admin/install', 'production-cache-avatar'),
                id='weblate.E008',
            )
        )

    return errors


def check_settings(app_configs, **kwargs):
    """Check for sane settings"""
    errors = []

    if (len(settings.ADMINS) == 0
            or 'noreply@weblate.org' in [x[1] for x in settings.ADMINS]):
        errors.append(
            Error(
                'The site admins seem to be wrongly configured',
                hint=get_doc_url('admin/install', 'production-admins'),
                id='weblate.E011',
            )
        )

    if settings.SERVER_EMAIL in DEFAULT_MAILS:
        errors.append(
            Critical(
                'The server email has default value',
                hint=get_doc_url('admin/install', 'production-email'),
                id='weblate.E012',
            )
        )
    if settings.DEFAULT_FROM_EMAIL in DEFAULT_MAILS:
        errors.append(
            Critical(
                'The default from email has default value',
                hint=get_doc_url('admin/install', 'production-email'),
                id='weblate.E013',
            )
        )

    if settings.SECRET_KEY == settings_example.SECRET_KEY:
        errors.append(
            Critical(
                'The cookie secret key has default value',
                hint=get_doc_url('admin/install', 'production-secret'),
                id='weblate.E014',
            )
        )

    if not settings.ALLOWED_HOSTS:
        errors.append(
            Critical(
                'The allowed hosts are not configured',
                hint=get_doc_url('admin/install', 'production-hosts'),
                id='weblate.E015',
            )
        )
    return errors


def check_templates(app_configs, **kwargs):
    """Check for sane settings"""
    errors = []

    if settings.TEMPLATES:
        loaders = settings.TEMPLATES[0].get(
            'OPTIONS', {}
        ).get(
            'loaders', [['']]
        )
    else:
        loaders = settings.TEMPLATE_LOADERS

    if isinstance(loaders[0], six.string_types):
        loader = loaders[0]
    else:
        loader = loaders[0][0]

    if 'cached.Loader' not in loader:
        errors.append(
            Error(
                'Configure cached template loader for better performance',
                hint=get_doc_url('admin/install', 'production-templates'),
                id='weblate.E016',
            )
        )
    return errors


def check_data_writable(app_configs=None, **kwargs):
    """Check we can write to data dir."""
    errors = []
    dirs = [
        settings.DATA_DIR,
        data_dir('home'),
        data_dir('whoosh'),
        data_dir('ssh'),
        data_dir('vcs'),
        data_dir('memory'),
        data_dir('celery'),
        data_dir('backups'),
    ]
    message = 'Path {} is not writable, check your DATA_DIR settings.'
    for path in dirs:
        if not os.path.exists(path):
            os.makedirs(path)
        elif not os.access(path, os.W_OK):
            errors.append(
                Critical(
                    message.format(path),
                    hint=get_doc_url('admin/install', 'file-permissions'),
                    id='weblate.E002',
                )
            )

    return errors


def check_site(app_configs, **kwargs):
    from weblate.utils.site import get_site_domain, check_domain
    errors = []
    if not check_domain(get_site_domain()):
        errors.append(
            Critical(
                'Configure correct site domain',
                hint=get_doc_url('admin/install', 'production-site'),
                id='weblate.E017',
            )
        )
    return errors
