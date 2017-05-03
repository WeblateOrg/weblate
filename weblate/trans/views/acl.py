# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from django.utils.translation import ugettext as _
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from weblate.utils import messages
from weblate.trans.util import render
from weblate.trans.forms import UserManageForm
from weblate.trans.views.helper import get_project
from weblate.permissions.helpers import can_manage_acl


def check_user_form(request, project, verbose=False):
    """Check project permission and UserManageForm.

    This is simple helper to perform needed validation for all
    user management views.
    """
    obj = get_project(request, project)

    if not can_manage_acl(request.user, obj):
        raise PermissionDenied()

    form = UserManageForm(request.POST)

    if form.is_valid():
        return obj, form
    elif verbose:
        for error in form.errors:
            for message in form.errors[error]:
                messages.error(request, message)
    return obj, None


@require_POST
@login_required
def set_groups(request, project):
    """Change group assignment for an user."""
    obj, form = check_user_form(request, project)

    try:
        group = Group.objects.get(
            groupacl__project=obj,
            pk=int(request.POST.get('group', '')),
        )
    except (Group.DoesNotExist, ValueError):
        group = None

    action = request.POST.get('action')

    user = form.cleaned_data['user'] if form else None

    if group is None or form is None:
        code = 400
        message = _('Invalid parameters!')
        status = None
    elif action == 'remove':
        if (group.name.endswith('@Administration') and
                obj.all_users('@Administration').count() <= 1):
            code = 400
            message = _('You can not remove last owner!')
        else:
            code = 200
            message = ''
            user.groups.remove(group)
        status = user.groups.filter(pk=group.pk).exists()
    else:
        user.groups.add(group)
        code = 200
        message = ''
        status = user.groups.filter(pk=group.pk).exists()

    return JsonResponse(
        data={
            'responseCode': code,
            'message': message,
            'state': status,
        }
    )


@require_POST
@login_required
def add_user(request, project):
    """Add user to a project."""
    obj, form = check_user_form(request, project, True)

    if form is not None:
        obj.add_user(form.cleaned_data['user'])
        messages.success(
            request, _('User has been added to this project.')
        )

    return redirect(
        'manage-access',
        project=obj.slug,
    )


@require_POST
@login_required
def delete_user(request, project):
    """Remove user from a project."""
    obj, form = check_user_form(request, project, True)

    if form is not None:
        owners = obj.all_users('@Administration')
        is_owner = owners.filter(pk=form.cleaned_data['user'].pk).exists()
        if is_owner and owners.count() <= 1:
            messages.error(request, _('You can not remove last owner!'))
        else:
            obj.remove_user(form.cleaned_data['user'])
            messages.success(
                request, _('User has been removed from this project.')
            )

    return redirect(
        'manage-access',
        project=obj.slug,
    )


@login_required
def manage_access(request, project):
    """User management view."""
    obj = get_project(request, project)

    if not can_manage_acl(request.user, obj):
        raise PermissionDenied()

    return render(
        request,
        'manage-access.html',
        {
            'object': obj,
            'project': obj,
            'groups': obj.all_groups(),
            'add_user_form': UserManageForm(),
        }
    )
