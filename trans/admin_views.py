# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from trans.models import SubProject
from django.contrib.sites.models import Site
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.translation import ugettext as _
from django.contrib import messages
from django.conf import settings
from weblate import appsettings
from trans.util import HAS_LIBRAVATAR
from accounts.forms import HAS_ICU
import weblate
import django

import os

# List of default domain names on which warn user
DEFAULT_DOMAINS = ('example.net', 'example.com')


@staff_member_required
def report(request):
    '''
    Provides report about git status of all repos.
    '''
    return render_to_response("admin/report.html", RequestContext(request, {
        'subprojects': SubProject.objects.all()
    }))


@staff_member_required
def performance(request):
    '''
    Shows performance tuning tips.
    '''
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
    # Check for sane caching
    cache = settings.CACHES['default']['BACKEND'].split('.')[-1]
    if cache in ['MemcachedCache', 'DatabaseCache']:
        # We consider these good
        cache = True
    elif cache in ['DummyCache']:
        # This one is definitely bad
        cache = False
    else:
        # These might not be that bad
        cache = None
    checks.append((
        _('Django caching'),
        cache,
        'production-cache',
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
            settings.SERVER_EMAIL not in default_mails
            and settings.DEFAULT_FROM_EMAIL not in default_mails
        ),
        'production-email',
    ))
    checks.append((
        _('Federated avatar support'),
        HAS_LIBRAVATAR,
        'production-avatar',
    ))
    checks.append((
        _('PyICU library'),
        HAS_ICU,
        'production-pyicu',
    ))
    if django.VERSION > (1, 5):
        checks.append((
            _('Allowed hosts'),
            len(settings.ALLOWED_HOSTS) > 0,
            'production-hosts',
        ))
    return render_to_response(
        "admin/performance.html",
        RequestContext(
            request,
            {
                'checks': checks,
            }
        )
    )


@staff_member_required
def ssh(request):
    '''
    Show information and manipulate with SSH key.
    '''
    # Path to key, we default to RSA keys
    key_path = os.path.expanduser('~/.ssh/id_rsa.pub')

    # Check whether we can generate SSH key
    try:
        ret = os.system('which ssh-keygen > /dev/null 2>&1')
        can_generate = (ret == 0 and not os.path.exists(key_path))
    except:
        can_generate = False

    # Generate key if it does not exist yet
    if can_generate and request.method == 'POST':
        try:
            ret = os.system(
                'ssh-keygen -q -N \'\' -C Weblate -t rsa -f %s' % key_path[:-4]
            )
            if ret != 0:
                messages.error(request, _('Failed to generate key!'))
            else:
                messages.info(request, _('Created new SSH key.'))
        except:
            messages.error(request, _('Failed to generate key!'))

    # Read key data if it exists
    if os.path.exists(key_path):
        key_data = file(key_path).read()
        key_type, key_fingerprint, key_id = key_data.strip().split(None, 2)
        key = {
            'key': key_data,
            'type': key_type,
            'fingerprint': key_fingerprint,
            'id': key_id,
        }
    else:
        key = None

    return render_to_response("admin/ssh.html", RequestContext(request, {
        'public_key': key,
        'can_generate': can_generate,
        'ssh_docs': weblate.get_doc_url('admin', 'private'),
    }))
