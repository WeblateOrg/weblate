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
from django.shortcuts import render, redirect
from django.utils.translation import ugettext as _

import six

from weblate.trans.models import Component, IndexUpdate
from weblate import settings_example
from weblate.accounts.avatar import HAS_LIBRAVATAR
from weblate.trans.util import HAS_PYUCA, check_domain
from weblate.trans.ssh import (
    generate_ssh_key, get_key_data, add_host_key,
    get_host_keys, can_generate_key
)
from weblate.utils import messages
from weblate.utils.site import get_site_url, get_site_domain
from weblate.wladmin.models import ConfigurationError

GOOD_CACHE = frozenset((
    'MemcachedCache', 'PyLibMCCache', 'DatabaseCache', 'RedisCache'
))


def report(request, admin_site):
    """Provide report about git status of all repos."""
    context = admin_site.each_context(request)
    context['components'] = Component.objects.all()
    return render(
        request,
        "admin/report.html",
        context,
    )


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


def handle_dismiss(request):
    try:
        error = ConfigurationError.objects.get(
            pk=int(request.POST['pk'])
        )
        if 'ignore' in request.POST:
            error.ignored = True
            error.save(update_fields=['ignored'])
        else:
            error.delete()
    except (ValueError, KeyError, ConfigurationError.DoesNotExist):
        messages.error(request, _('Failed to dismiss configuration error!'))
    return redirect('admin:performance')


def performance(request, admin_site):
    """Show performance tuning tips."""
    if request.method == 'POST':
        return handle_dismiss(request)
    checks = []
    # Check for debug mode
    checks.append((
        _('Debug mode'),
        not settings.DEBUG,
        'production-debug',
        settings.DEBUG,
    ))
    # Check for domain configuration
    checks.append((
        _('Site domain'),
        check_domain(get_site_domain()),
        'production-site',
        get_site_url(),
    ))
    # Check database being used
    checks.append((
        _('Database backend'),
        "sqlite" not in settings.DATABASES['default']['ENGINE'],
        'production-database',
        settings.DATABASES['default']['ENGINE'],
    ))
    # Check configured admins
    checks.append((
        _('Site administrator'),
        len(settings.ADMINS) > 0 or
        'noreply@weblate.org' in [x[1] for x in settings.ADMINS],
        'production-admins',
        ', '.join([x[1] for x in settings.ADMINS]),
    ))
    # Check offloading indexing
    checks.append((
        # Translators: Indexing is postponed to cron job
        _('Indexing offloading'),
        settings.OFFLOAD_INDEXING,
        'production-indexing',
        settings.OFFLOAD_INDEXING
    ))
    if settings.OFFLOAD_INDEXING:
        if IndexUpdate.objects.count() < 20:
            index_updates = True
        elif IndexUpdate.objects.count() < 200:
            index_updates = None
        else:
            index_updates = False

        checks.append((
            # Translators: Indexing is postponed to cron job
            _('Indexing offloading processing'),
            index_updates,
            'production-indexing',
            IndexUpdate.objects.count(),
        ))
    # Check for sane caching
    caches = settings.CACHES['default']['BACKEND'].split('.')[-1]
    if caches in GOOD_CACHE:
        # We consider these good
        caches = True
    elif caches in ['DummyCache']:
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
    # Avatar caching
    checks.append((
        _('Avatar caching'),
        'avatar' in settings.CACHES,
        'production-cache-avatar',
        settings.CACHES['avatar']['BACKEND']
        if 'avatar' in settings.CACHES else '',
    ))
    # Check email setup
    default_mails = (
        'root@localhost',
        'webmaster@localhost',
        'noreply@weblate.org'
        'noreply@example.com'
    )
    checks.append((
        _('Email addresses'),
        (
            settings.SERVER_EMAIL not in default_mails and
            settings.DEFAULT_FROM_EMAIL not in default_mails
        ),
        'production-email',
        ', '.join((settings.SERVER_EMAIL, settings.DEFAULT_FROM_EMAIL)),
    ))
    # libravatar library
    checks.append((
        _('Federated avatar support'),
        HAS_LIBRAVATAR,
        'production-avatar',
        HAS_LIBRAVATAR,
    ))
    # pyuca library
    checks.append((
        _('pyuca library'),
        HAS_PYUCA,
        'production-pyuca',
        HAS_PYUCA,
    ))
    # Cookie signing key
    checks.append((
        _('Secret key'),
        settings.SECRET_KEY != settings_example.SECRET_KEY,
        'production-secret',
        '',
    ))
    # Allowed hosts
    checks.append((
        _('Allowed hosts'),
        len(settings.ALLOWED_HOSTS) > 0,
        'production-hosts',
        ', '.join(settings.ALLOWED_HOSTS),
    ))

    loader = get_first_loader()
    # Cached template loader
    checks.append((
        _('Cached template loader'),
        'cached.Loader' in loader,
        'production-templates',
        loader,
    ))

    # Check for serving static files
    checks.append((
        _('Admin static files'),
        os.path.exists(
            os.path.join(settings.STATIC_ROOT, 'admin', 'js', 'core.js')
        ),
        'production-admin-files',
        settings.STATIC_ROOT,
    ))

    context = admin_site.each_context(request)
    context['checks'] = checks
    context['errors'] = ConfigurationError.objects.filter(ignored=False)

    return render(
        request,
        "admin/performance.html",
        context,
    )


def ssh(request, admin_site):
    """Show information and manipulate with SSH key."""
    # Check whether we can generate SSH key
    can_generate = can_generate_key()

    # Grab action type
    action = request.POST.get('action')

    # Generate key if it does not exist yet
    if can_generate and action == 'generate':
        generate_ssh_key(request)

    # Read key data if it exists
    key = get_key_data()

    # Add host key
    if action == 'add-host':
        add_host_key(request)

    context = admin_site.each_context(request)
    context['public_key'] = key
    context['can_generate'] = can_generate
    context['host_keys'] = get_host_keys()

    return render(
        request,
        "admin/ssh.html",
        context,
    )
