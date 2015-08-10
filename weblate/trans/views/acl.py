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

from django.utils.translation import ugettext as _
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.contrib.auth.models import User
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied

from weblate.trans.util import redirect_param
from weblate.trans.forms import AddUserForm
from weblate.trans.views.helper import get_project
from weblate.trans.permissions import can_manage_acl


@require_POST
@login_required
def add_user(request, project):
    obj = get_project(request, project)

    if not can_manage_acl(request.user, obj):
        raise PermissionDenied()

    form = AddUserForm(request.POST)

    if form.is_valid():
        try:
            user = User.objects.get(
                Q(username=form.cleaned_data['name']) |
                Q(email=form.cleaned_data['name'])
            )
            obj.add_user(user)
            messages.success(
                request, _('User has been added to this project.')
            )
        except User.DoesNotExist:
            messages.error(request, _('No matching user found!'))
        except User.MultipleObjectsReturned:
            messages.error(request, _('More users matched!'))
    else:
        messages.error(request, _('Invalid user specified!'))

    return redirect_param(
        'project',
        '#acl',
        project=obj.slug,
    )


@require_POST
@login_required
def delete_user(request, project):
    obj = get_project(request, project)

    if not can_manage_acl(request.user, obj):
        raise PermissionDenied()

    form = AddUserForm(request.POST)

    if form.is_valid():
        try:
            user = User.objects.get(
                username=form.cleaned_data['name']
            )
            obj.remove_user(user)
            messages.success(
                request, _('User has been removed from this project.')
            )
        except User.DoesNotExist:
            messages.error(request, _('No matching user found!'))
        except User.MultipleObjectsReturned:
            messages.error(request, _('More users matched!'))
    else:
        messages.error(request, _('Invalid user specified!'))

    return redirect_param(
        'project',
        '#acl',
        project=obj.slug,
    )
