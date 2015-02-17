# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from weblate.trans.models import SubProject, IndexUpdate
from django.contrib.sites.models import Site
from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.translation import ugettext as _
from django.conf import settings
from weblate import settings_example
from weblate import appsettings
from weblate.accounts.avatar import HAS_LIBRAVATAR
from weblate.accounts.forms import HAS_PYUCA
from weblate.trans.util import get_configuration_errors
from weblate.trans.ssh import (
    generate_ssh_key, get_key_data, add_host_key,
    get_host_keys, can_generate_key
)
import weblate

# List of default domain names on which warn user
DEFAULT_DOMAINS = ('example.net', 'example.com')


@staff_member_required
def report(request):
    """
    Provides report about git status of all repos.
    """
    return render(
        request,
        "admin/report.html",
        {
            'subprojects': SubProject.objects.all()
        }
    )


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
    ))
    # Check for domain configuration
    checks.append((
        _('Site domain'),
        Site.objects.get_current().domain not in DEFAULT_DOMAINS,
        'production-site',
    ))
    # Check database being used
    checks.append((
        _('Database backend'),
        "sqlite" not in settings.DATABASES['default']['ENGINE'],
        'production-database',
    ))
    # Check configured admins
    checks.append((
        _('Site administrator'),
        len(settings.ADMINS) > 0,
        'production-admins',
    ))
    # Check offloading indexing
    checks.append((
        # Translators: Indexing is postponed to cron job
        _('Indexing offloading'),
        appsettings.OFFLOAD_INDEXING,
        'production-indexing',
    ))
    if appsettings.OFFLOAD_INDEXING:
        checks.append((
            # Translators: Indexing is postponed to cron job
            _('Indexing offloading processing'),
            IndexUpdate.objects.count() < 20,
            'production-indexing',
        ))
    # Check for sane caching
    caches = settings.CACHES['default']['BACKEND'].split('.')[-1]
    if caches in ['MemcachedCache', 'DatabaseCache']:
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
    ))
    # Avatar caching
    checks.append((
        _('Avatar caching'),
        'avatar' in settings.CACHES,
        'production-cache-avatar',
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
    ))
    # libravatar library
    checks.append((
        _('Federated avatar support'),
        HAS_LIBRAVATAR,
        'production-avatar',
    ))
    # pyuca library
    checks.append((
        _('pyuca library'),
        HAS_PYUCA,
        'production-pyuca',
    ))
    # Cookie signing key
    checks.append((
        _('Secret key'),
        settings.SECRET_KEY != settings_example.SECRET_KEY,
        'production-secret',
    ))
    # Allowed hosts
    checks.append((
        _('Allowed hosts'),
        len(settings.ALLOWED_HOSTS) > 0,
        'production-hosts',
    ))

    # Cached template loader
    checks.append((
        _('Cached template loader'),
        'cached.Loader' in settings.TEMPLATE_LOADERS[0][0],
        'production-templates'
    ))

    # Check for serving static files
    # This uses CSS magic to hide this check when CSS is properly loaded.
    checks.append((
        _('Admin static files'),
        False,
        'production-admin-files',
        'order-cell',
    ))

    return render(
        request,
        "admin/performance.html",
        {
            'checks': checks,
            'errors': get_configuration_errors()
        }
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

    return render(
        request,
        "admin/ssh.html",
        {
            'public_key': key,
            'can_generate': can_generate,
            'host_keys': get_host_keys(),
            'ssh_docs': weblate.get_doc_url('admin/projects', 'private'),
        }
    )
