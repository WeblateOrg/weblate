#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from filelock import Timeout

from weblate.trans.util import redirect_param
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.views import get_component, get_project, get_translation


def execute_locked(request, obj, message, call, *args, **kwargs):
    """Helper function to catch possible lock exception."""
    try:
        result = call(*args, **kwargs)
        # With False the call is supposed to show errors on its own
        if result is None or result:
            messages.success(request, message)
    except Timeout:
        messages.error(
            request,
            _("Failed to lock the repository, another operation is in progress."),
        )
        report_error()

    return redirect_param(obj, "#repository")


def perform_commit(request, obj):
    """Helper function to do the repository commmit."""
    return execute_locked(
        request,
        obj,
        _("All pending translations were committed."),
        obj.commit_pending,
        "commit",
        request.user,
    )


def perform_update(request, obj):
    """Helper function to do the repository update."""
    return execute_locked(
        request,
        obj,
        _("All repositories were updated."),
        obj.do_update,
        request,
        method=request.GET.get("method"),
    )


def perform_push(request, obj):
    """Helper function to do the repository push."""
    return execute_locked(
        request, obj, _("All repositories were pushed."), obj.do_push, request
    )


def perform_reset(request, obj):
    """Helper function to do the repository reset."""
    return execute_locked(
        request, obj, _("All repositories have been reset."), obj.do_reset, request
    )


def perform_cleanup(request, obj):
    """Helper function to do the repository cleanup."""
    return execute_locked(
        request,
        obj,
        _("All repositories have been cleaned up."),
        obj.do_cleanup,
        request,
    )


@login_required
@require_POST
def commit_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("vcs.commit", obj):
        raise PermissionDenied()

    return perform_commit(request, obj)


@login_required
@require_POST
def commit_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("vcs.commit", obj):
        raise PermissionDenied()

    return perform_commit(request, obj)


@login_required
@require_POST
def commit_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("vcs.commit", obj):
        raise PermissionDenied()

    return perform_commit(request, obj)


@login_required
@require_POST
def update_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("vcs.update", obj):
        raise PermissionDenied()

    return perform_update(request, obj)


@login_required
@require_POST
def update_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("vcs.update", obj):
        raise PermissionDenied()

    return perform_update(request, obj)


@login_required
@require_POST
def update_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("vcs.update", obj):
        raise PermissionDenied()

    return perform_update(request, obj)


@login_required
@require_POST
def push_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("vcs.push", obj):
        raise PermissionDenied()

    return perform_push(request, obj)


@login_required
@require_POST
def push_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("vcs.push", obj):
        raise PermissionDenied()

    return perform_push(request, obj)


@login_required
@require_POST
def push_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("vcs.push", obj):
        raise PermissionDenied()

    return perform_push(request, obj)


@login_required
@require_POST
def reset_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied()

    return perform_reset(request, obj)


@login_required
@require_POST
def reset_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied()

    return perform_reset(request, obj)


@login_required
@require_POST
def reset_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied()

    return perform_reset(request, obj)


@login_required
@require_POST
def cleanup_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied()

    return perform_cleanup(request, obj)


@login_required
@require_POST
def cleanup_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied()

    return perform_cleanup(request, obj)


@login_required
@require_POST
def cleanup_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied()

    return perform_cleanup(request, obj)
