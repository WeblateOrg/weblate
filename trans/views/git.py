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

from django.utils.translation import ugettext as _
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required, permission_required
from trans.views.helper import get_project, get_subproject, get_translation


@login_required
@permission_required('trans.commit_translation')
def commit_project(request, project):
    obj = get_project(request, project)
    obj.commit_pending(request)

    messages.info(request, _('All pending translations were committed.'))

    return redirect(obj)


@login_required
@permission_required('trans.commit_translation')
def commit_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)
    obj.commit_pending(request)

    messages.info(request, _('All pending translations were committed.'))

    return redirect(obj)


@login_required
@permission_required('trans.commit_translation')
def commit_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)
    obj.commit_pending(request)

    messages.info(request, _('All pending translations were committed.'))

    return redirect(obj)


@login_required
@permission_required('trans.update_translation')
def update_project(request, project):
    obj = get_project(request, project)

    if obj.do_update(request):
        messages.info(request, _('All repositories were updated.'))

    return redirect(obj)


@login_required
@permission_required('trans.update_translation')
def update_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    if obj.do_update(request):
        messages.info(request, _('All repositories were updated.'))

    return redirect(obj)


@login_required
@permission_required('trans.update_translation')
def update_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if obj.do_update(request):
        messages.info(request, _('All repositories were updated.'))

    return redirect(obj)


@login_required
@permission_required('trans.push_translation')
def push_project(request, project):
    obj = get_project(request, project)

    if obj.do_push(request):
        messages.info(request, _('All repositories were pushed.'))

    return redirect(obj)


@login_required
@permission_required('trans.push_translation')
def push_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    if obj.do_push(request):
        messages.info(request, _('All repositories were pushed.'))

    return redirect(obj)


@login_required
@permission_required('trans.push_translation')
def push_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if obj.do_push(request):
        messages.info(request, _('All repositories were pushed.'))

    return redirect(obj)


@login_required
@permission_required('trans.reset_translation')
def reset_project(request, project):
    obj = get_project(request, project)

    if obj.do_reset(request):
        messages.info(request, _('All repositories have been reset.'))

    return redirect(obj)


@login_required
@permission_required('trans.reset_translation')
def reset_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    if obj.do_reset(request):
        messages.info(request, _('All repositories have been reset.'))

    return redirect(obj)


@login_required
@permission_required('trans.reset_translation')
def reset_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if obj.do_reset(request):
        messages.info(request, _('All repositories have been reset.'))

    return redirect(obj)
