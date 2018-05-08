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

from django.utils.translation import ugettext as _
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST

from weblate.utils import messages
from weblate.trans.util import redirect_param
from weblate.trans.views.helper import get_project, get_component


@require_POST
@login_required
def lock_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm('component.lock', obj):
        raise PermissionDenied()

    obj.commit_pending(request)

    obj.do_lock(request.user)

    messages.success(
        request,
        _('Component is now locked for translation updates!')
    )

    return redirect_param(obj, '#repository')


@require_POST
@login_required
def unlock_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm('component.lock', obj):
        raise PermissionDenied()

    obj.do_lock(request.user, False)

    messages.success(
        request,
        _('Component is now open for translation updates.')
    )

    return redirect_param(obj, '#repository')


@require_POST
@login_required
def lock_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm('component.lock', obj):
        raise PermissionDenied()

    obj.commit_pending(request)

    for component in obj.component_set.all():
        component.do_lock(request.user)

    messages.success(
        request,
        _('All components are now locked for translation updates!')
    )

    return redirect_param(obj, '#repository')


@require_POST
@login_required
def unlock_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm('component.lock', obj):
        raise PermissionDenied()

    for component in obj.component_set.all():
        component.do_lock(request.user, False)

    messages.success(
        request,
        _('Project is now open for translation updates.')
    )

    return redirect_param(obj, '#repository')
