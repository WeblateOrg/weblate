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

import sys

from django.utils.translation import ugettext as _
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from weblate.utils import messages
from weblate.trans.views.helper import (
    get_project, get_subproject, get_translation
)
from weblate.trans.filelock import FileLockException
from weblate.trans.util import redirect_param
from weblate.permissions.helpers import (
    can_commit_translation, can_update_translation, can_reset_translation,
    can_push_translation, can_remove_translation,
)
from weblate.utils.errors import report_error


def execute_locked(request, obj, message, call, *args, **kwargs):
    """Helper function to catch possible lock exception."""
    try:
        result = call(*args, **kwargs)
        # With False the call is supposed to show errors on its own
        if result is None or result:
            messages.success(request, message)
    except FileLockException as error:
        messages.error(
            request,
            _('Failed to lock the repository, another operation in progress.')
        )
        report_error(
            error, sys.exc_info(),
        )

    return redirect_param(obj, '#repository')


def perform_commit(request, obj):
    """Helper function to do the repository commmit."""
    return execute_locked(
        request,
        obj,
        _('All pending translations were committed.'),
        obj.commit_pending,
        request,
    )


def perform_update(request, obj):
    """Helper function to do the repository update."""
    return execute_locked(
        request,
        obj,
        _('All repositories were updated.'),
        obj.do_update,
        request,
        method=request.GET.get('method'),
    )


def perform_push(request, obj):
    """Helper function to do the repository push."""
    return execute_locked(
        request,
        obj,
        _('All repositories were pushed.'),
        obj.do_push,
        request,
    )


def perform_reset(request, obj):
    """Helper function to do the repository reset."""
    return execute_locked(
        request,
        obj,
        _('All repositories have been reset.'),
        obj.do_reset,
        request,
    )


@login_required
@require_POST
def commit_project(request, project):
    obj = get_project(request, project)

    if not can_commit_translation(request.user, obj):
        raise PermissionDenied()

    return perform_commit(request, obj)


@login_required
@require_POST
def commit_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    if not can_commit_translation(request.user, obj.project):
        raise PermissionDenied()

    return perform_commit(request, obj)


@login_required
@require_POST
def commit_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not can_commit_translation(request.user, obj.subproject.project):
        raise PermissionDenied()

    return perform_commit(request, obj)


@login_required
@require_POST
def update_project(request, project):
    obj = get_project(request, project)

    if not can_update_translation(request.user, obj):
        raise PermissionDenied()

    return perform_update(request, obj)


@login_required
@require_POST
def update_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    if not can_update_translation(request.user, obj.project):
        raise PermissionDenied()

    return perform_update(request, obj)


@login_required
@require_POST
def update_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not can_update_translation(request.user, obj.subproject.project):
        raise PermissionDenied()

    return perform_update(request, obj)


@login_required
@require_POST
def push_project(request, project):
    obj = get_project(request, project)

    if not can_push_translation(request.user, obj):
        raise PermissionDenied()

    return perform_push(request, obj)


@login_required
@require_POST
def push_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    if not can_push_translation(request.user, obj.project):
        raise PermissionDenied()

    return perform_push(request, obj)


@login_required
@require_POST
def push_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not can_push_translation(request.user, obj.subproject.project):
        raise PermissionDenied()

    return perform_push(request, obj)


@login_required
@require_POST
def reset_project(request, project):
    obj = get_project(request, project)

    if not can_reset_translation(request.user, obj):
        raise PermissionDenied()

    return perform_reset(request, obj)


@login_required
@require_POST
def reset_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    if not can_reset_translation(request.user, obj.project):
        raise PermissionDenied()

    return perform_reset(request, obj)


@login_required
@require_POST
def reset_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not can_reset_translation(request.user, obj.subproject.project):
        raise PermissionDenied()

    return perform_reset(request, obj)


@login_required
@require_POST
def remove_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not can_remove_translation(request.user, obj.subproject.project):
        raise PermissionDenied()

    return execute_locked(
        request,
        obj.subproject,
        _('Translation has been removed.'),
        obj.remove,
        user=request.user,
    )
