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

from django.core.checks import run_checks
from django.shortcuts import render, redirect
from django.utils.translation import ugettext as _

from weblate.trans.models import Component
from weblate.vcs.ssh import (
    generate_ssh_key, get_key_data, add_host_key,
    get_host_keys, can_generate_key
)
from weblate.utils import messages
from weblate.wladmin.models import ConfigurationError
from weblate.wladmin.performance import run_checks as wl_run_checks


def report(request, admin_site):
    """Provide report about git status of all repos."""
    context = admin_site.each_context(request)
    context['components'] = Component.objects.all()
    return render(
        request,
        "admin/report.html",
        context,
    )


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

    context = admin_site.each_context(request)
    context['checks'] = wl_run_checks(request)
    context['django_errors'] = run_checks(include_deployment_checks=True)
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
