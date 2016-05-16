# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import os.path

from django.contrib.sites.models import Site
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import admin
from django.utils.translation import ugettext as _
from django.conf import settings
import django

import six

from weblate.trans.models import SubProject, IndexUpdate
from weblate import settings_example
from weblate import appsettings
from weblate.accounts.avatar import HAS_LIBRAVATAR
from weblate.trans.util import get_configuration_errors, HAS_PYUCA
from weblate.trans.ssh import (
    generate_ssh_key, get_key_data, add_host_key,
    get_host_keys, can_generate_key
)
import weblate

# List of default domain names on which warn user
DEFAULT_DOMAINS = ('example.net', 'example.com')


def admin_context(request):
    """Wrapper to get admin context"""
    # Django has changed number of parameters
    # pylint: disable=E1120
    if django.VERSION < (1, 8, 0):
        return admin.site.each_context()
    return admin.site.each_context(request)


@staff_member_required
def report(request):
    """
    Provides report about git status of all repos.
    """
    context = admin_context(request)
    context['subprojects'] = SubProject.objects.all()
    return render(
        request,
        "admin/report.html",
        context,
    )


def get_first_loader():
    """Returns first loader from settings"""
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


@staff_member_required
def performance(request):
    """
    Shows performance tuning tips.
    """
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
        Site.objects.get_current().domain not in DEFAULT_DOMAINS,
        'production-site',
        Site.objects.get_current().domain,
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
        appsettings.OFFLOAD_INDEXING,
        'production-indexing',
        appsettings.OFFLOAD_INDEXING
    ))
    if appsettings.OFFLOAD_INDEXING:
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
    if caches in ['MemcachedCache', 'PyLibMCCache', 'DatabaseCache']:
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
        settings.SECRET_KEY,
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

    context = admin_context(request)
    context['checks'] = checks
    context['errors'] = get_configuration_errors()

    return render(
        request,
        "admin/performance.html",
        context,
    )


@staff_member_required
def ssh(request):
    """
    Show information and manipulate with SSH key.
    """
    # Check whether we can generate SSH key
    can_generate = can_generate_key()

    # Grab action type
    action = request.POST.get('action', None)

    # Generate key if it does not exist yet
    if can_generate and action == 'generate':
        generate_ssh_key(request)

    # Read key data if it exists
    key = get_key_data()

    # Add host key
    if action == 'add-host':
        add_host_key(request)

    context = admin_context(request)
    context['public_key'] = key
    context['can_generate'] = can_generate
    context['host_keys'] = get_host_keys()
    context['ssh_docs'] = weblate.get_doc_url('admin/projects', 'private')

    return render(
        request,
        "admin/ssh.html",
        context,
    )
