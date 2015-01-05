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
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from weblate.trans.views.helper import (
    get_project, get_subproject, get_translation
)
from weblate.trans.filelock import FileLockException
from weblate.trans.util import redirect_param


def execute_locked(request, obj, message, call, *args, **kwargs):
    """
    Helper function to catch possible lock exception.
    """
    try:
        result = call(request, *args, **kwargs)
        # With False the call is supposed to show errors on it's own
        if result is None or result:
            messages.success(request, message)
    except FileLockException:
        messages.error(
            request,
            _('Failed to lock the repository, another operation in progress.')
        )

    return redirect_param(obj, '#repository')


def perform_commit(request, obj):
    """
    Helper function to do the repository commmit.
    """
    return execute_locked(
        request,
        obj,
        _('All pending translations were committed.'),
        obj.commit_pending,
    )


def perform_update(request, obj):
    """
    Helper function to do the repository update.
    """
    return execute_locked(
        request,
        obj,
        _('All repositories were updated.'),
        obj.do_update,
        method=request.GET.get('method', None)
    )


def perform_push(request, obj):
    """
    Helper function to do the repository push.
    """
    return execute_locked(
        request,
        obj,
        _('All repositories were pushed.'),
        obj.do_push
    )


def perform_reset(request, obj):
    """
    Helper function to do the repository reset.
    """
    return execute_locked(
        request,
        obj,
        _('All repositories have been reset.'),
        obj.do_reset
    )


@login_required
@permission_required('trans.commit_translation')
def commit_project(request, project):
    obj = get_project(request, project)

    return perform_commit(request, obj)


@login_required
@permission_required('trans.commit_translation')
def commit_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    return perform_commit(request, obj)


@login_required
@permission_required('trans.commit_translation')
def commit_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    return perform_commit(request, obj)


@login_required
@permission_required('trans.update_translation')
def update_project(request, project):
    obj = get_project(request, project)

    return perform_update(request, obj)


@login_required
@permission_required('trans.update_translation')
def update_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    return perform_update(request, obj)


@login_required
@permission_required('trans.update_translation')
def update_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    return perform_update(request, obj)


@login_required
@permission_required('trans.push_translation')
def push_project(request, project):
    obj = get_project(request, project)

    return perform_push(request, obj)


@login_required
@permission_required('trans.push_translation')
def push_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    return perform_push(request, obj)


@login_required
@permission_required('trans.push_translation')
def push_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    return perform_push(request, obj)


@login_required
@permission_required('trans.reset_translation')
def reset_project(request, project):
    obj = get_project(request, project)

    return perform_reset(request, obj)


@login_required
@permission_required('trans.reset_translation')
def reset_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    return perform_reset(request, obj)


@login_required
@permission_required('trans.reset_translation')
def reset_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    return perform_reset(request, obj)
