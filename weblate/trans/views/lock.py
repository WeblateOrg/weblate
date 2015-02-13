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
from django.http import HttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required

from weblate.trans.views.helper import (
    get_project, get_subproject, get_translation
)


@login_required
@permission_required('trans.lock_translation')
def lock_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not obj.is_user_locked(request):
        obj.create_lock(request.user, True)
        messages.success(request, _('Translation is now locked for you.'))

    return redirect(obj)


@login_required
def update_lock(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not obj.is_user_locked(request):
        obj.update_lock_time()

    return HttpResponse('ok')


@login_required
@permission_required('trans.lock_translation')
def unlock_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not obj.is_user_locked(request):
        obj.create_lock(None)
        messages.success(
            request,
            _('Translation is now open for translation updates.')
        )

    return redirect(obj)


@login_required
@permission_required('trans.lock_subproject')
def lock_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    obj.commit_pending(request)

    obj.do_lock(request.user)

    messages.success(
        request,
        _('Component is now locked for translation updates!')
    )

    return redirect(obj)


@login_required
@permission_required('trans.lock_subproject')
def unlock_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    obj.do_unlock(request.user)

    messages.success(
        request,
        _('Component is now open for translation updates.')
    )

    return redirect(obj)


@login_required
@permission_required('trans.lock_subproject')
def lock_project(request, project):
    obj = get_project(request, project)

    obj.commit_pending(request)

    for subproject in obj.subproject_set.all():
        subproject.do_lock(request.user)

    messages.success(
        request,
        _('All subprojects are now locked for translation updates!')
    )

    return redirect(obj)


@login_required
@permission_required('trans.lock_subproject')
def unlock_project(request, project):
    obj = get_project(request, project)

    for subproject in obj.subproject_set.all():
        subproject.do_unlock(request.user)

    messages.success(
        request,
        _('Project is now open for translation updates.')
    )

    return redirect(obj)
