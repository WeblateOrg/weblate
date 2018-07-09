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
from django.utils.translation import ugettext as _

import six

from weblate.trans.models import IndexUpdate
from weblate import settings_example
from weblate.trans.util import HAS_PYUCA, check_domain
from weblate.utils.site import get_site_url, get_site_domain

DEFAULT_MAILS = frozenset((
    'root@localhost',
    'webmaster@localhost',
    'noreply@weblate.org'
    'noreply@example.com'
))

GOOD_CACHE = frozenset((
    'MemcachedCache', 'PyLibMCCache', 'DatabaseCache', 'RedisCache'
))
BAD_CACHE = frozenset((
    'DummyCache', 'LocMemCache',
))

PERFORMANCE_CHECKS = []


def register_check(function):
    PERFORMANCE_CHECKS.append(function)
    return function


def run_checks(request):
    result = []
    for check in PERFORMANCE_CHECKS:
        check(result, request)
    return result


@register_check
def run_debug(checks, request):
    """Check for debug mode"""
    checks.append((
        _('Debug mode'),
        not settings.DEBUG,
        'production-debug',
        settings.DEBUG,
    ))


@register_check
def run_server(checks, request):
    """Detect Django built in server."""
    server = request.META.get('SERVER_SOFTWARE', None)
    if server:
        checks.append((
            _('Server'),
            not server.startswith('WSGIServer/'),
            'server',
            server,
        ))


@register_check
def run_domain(checks, request):
    """Check for domain configuration"""
    checks.append((
        _('Site domain'),
        check_domain(get_site_domain()),
        'production-site',
        get_site_url(),
    ))


@register_check
def run_db(checks, request):
    """Check database being used"""
    checks.append((
        _('Database backend'),
        "sqlite" not in settings.DATABASES['default']['ENGINE'],
        'production-database',
        settings.DATABASES['default']['ENGINE'],
    ))


@register_check
def run_admin(checks, request):
    """Check configured admins"""
    checks.append((
        _('Site administrator'),
        len(settings.ADMINS) > 0 or
        'noreply@weblate.org' in [x[1] for x in settings.ADMINS],
        'production-admins',
        ', '.join([x[1] for x in settings.ADMINS]),
    ))


@register_check
def run_index(checks, request):
    """Check offloading indexing"""
    checks.append((
        # Translators: Indexing is postponed to cron job
        _('Indexing offloading'),
        settings.OFFLOAD_INDEXING,
        'production-indexing',
        settings.OFFLOAD_INDEXING
    ))


@register_check
def run_index_queue(checks, request):
    if settings.OFFLOAD_INDEXING:
        if IndexUpdate.objects.count() < 1000:
            index_updates = True
        elif IndexUpdate.objects.count() < 20000:
            index_updates = None
        else:
            index_updates = False

        checks.append((
            # Translators: Indexing is postponed to cron job
            _('Indexing offloading queue'),
            index_updates,
            'production-indexing',
            IndexUpdate.objects.count(),
        ))


@register_check
def run_cache(checks, request):
    """Check for sane caching"""
    caches = settings.CACHES['default']['BACKEND'].split('.')[-1]
    if caches in GOOD_CACHE:
        # We consider these good
        caches = True
    elif caches in BAD_CACHE:
        # This one is definitely bad
        caches = False
    else:
        # These might not be that bad
        caches = None
    checks.append((
        _('Django caching'),
        caches,
        'production-cache',
        settings.CACHES['default']['BACKEND'],
    ))


@register_check
def run_avatar_cache(checks, request):
    """Avatar caching"""
    checks.append((
        _('Avatar caching'),
        'avatar' in settings.CACHES,
        'production-cache-avatar',
        settings.CACHES['avatar']['BACKEND']
        if 'avatar' in settings.CACHES else '',
    ))


@register_check
def run_mails(checks, request):
    """Check email setup"""
    checks.append((
        _('Email addresses'),
        (
            settings.SERVER_EMAIL not in DEFAULT_MAILS and
            settings.DEFAULT_FROM_EMAIL not in DEFAULT_MAILS
        ),
        'production-email',
        ', '.join((settings.SERVER_EMAIL, settings.DEFAULT_FROM_EMAIL)),
    ))


@register_check
def run_pyuca(checks, request):
    """pyuca library"""
    checks.append((
        _('pyuca library'),
        HAS_PYUCA,
        'production-pyuca',
        HAS_PYUCA,
    ))


@register_check
def run_cookies(checks, request):
    """Cookie signing key"""
    checks.append((
        _('Secret key'),
        settings.SECRET_KEY != settings_example.SECRET_KEY,
        'production-secret',
        '',
    ))


@register_check
def run_hosts(checks, request):
    """Allowed hosts"""
    checks.append((
        _('Allowed hosts'),
        len(settings.ALLOWED_HOSTS) > 0,
        'production-hosts',
        ', '.join(settings.ALLOWED_HOSTS),
    ))


def get_first_loader():
    """Return first loader from settings"""
    if settings.TEMPLATES:
        loaders = settings.TEMPLATES[0].get(
            'OPTIONS', {}
        ).get(
            'loaders', [['']]
        )
    else:
        loaders = settings.TEMPLATE_LOADERS

    if isinstance(loaders[0], six.string_types):
        return loaders[0]

    return loaders[0][0]


@register_check
def run_templates(checks, request):
    """Cached template loader"""
    loader = get_first_loader()
    checks.append((
        _('Cached template loader'),
        'cached.Loader' in loader,
        'production-templates',
        loader,
    ))


@register_check
def run_static(checks, request):
    """Check for serving static files"""
    checks.append((
        _('Admin static files'),
        os.path.exists(
            os.path.join(settings.STATIC_ROOT, 'admin', 'js', 'core.js')
        ),
        'production-admin-files',
        settings.STATIC_ROOT,
    ))
