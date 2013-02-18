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

from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext as _
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required

from weblate.trans.models import Project, SubProject, Translation


@login_required
@permission_required('trans.lock_translation')
def lock_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if not obj.is_user_locked(request):
        obj.create_lock(request.user, True)
        messages.info(request, _('Translation is now locked for you.'))

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
def update_lock(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if not obj.is_user_locked(request):
        obj.update_lock_time()

    return HttpResponse('ok')


@login_required
@permission_required('trans.lock_translation')
def unlock_translation(request, project, subproject, lang):
    obj = get_object_or_404(
        Translation,
        language__code=lang,
        subproject__slug=subproject,
        subproject__project__slug=project,
        enabled=True
    )
    obj.check_acl(request)

    if not obj.is_user_locked(request):
        obj.create_lock(None)
        messages.info(
            request,
            _('Translation is now open for translation updates.')
        )

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.lock_subproject')
def lock_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    obj.commit_pending()

    obj.locked = True
    obj.save()

    messages.info(
        request,
        _('Subproject is now locked for translation updates!')
    )

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.lock_subproject')
def unlock_subproject(request, project, subproject):
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    obj.check_acl(request)

    obj.locked = False
    obj.save()

    messages.info(
        request,
        _('Subproject is now open for translation updates.')
    )

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.lock_subproject')
def lock_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    obj.commit_pending()

    for subproject in obj.subproject_set.all():
        subproject.locked = True
        subproject.save()

    messages.info(
        request,
        _('All subprojects are now locked for translation updates!')
    )

    return HttpResponseRedirect(obj.get_absolute_url())


@login_required
@permission_required('trans.lock_subproject')
def unlock_project(request, project):
    obj = get_object_or_404(Project, slug=project)
    obj.check_acl(request)

    for subproject in obj.subproject_set.all():
        subproject.locked = False
        subproject.save()

    messages.info(request, _('Project is now open for translation updates.'))

    return HttpResponseRedirect(obj.get_absolute_url())
