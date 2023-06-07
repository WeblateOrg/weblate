# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from weblate.trans.models import Component, Project
from weblate.trans.util import redirect_param
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.lock import WeblateLockTimeout
from weblate.utils.views import get_component, get_project, get_translation


def execute_locked(request, obj, message, call, *args, **kwargs):
    """Helper function to catch possible lock exception."""
    try:
        result = call(*args, **kwargs)
        # With False the call is supposed to show errors on its own
        if result is None or result:
            messages.success(request, message)
    except WeblateLockTimeout:
        messages.error(
            request,
            gettext("Failed to lock the repository, another operation is in progress."),
        )
        if isinstance(obj, Project):
            report_error(project=obj)
        elif isinstance(obj, Component):
            report_error(project=obj.project)
        else:
            report_error(project=obj.component.project)

    return redirect_param(obj, "#repository")


def perform_commit(request, obj):
    """Helper function to do the repository commit."""
    if not request.user.has_perm("vcs.commit", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("All pending translations were committed."),
        obj.commit_pending,
        "commit",
        request.user,
    )


def perform_update(request, obj):
    """Helper function to do the repository update."""
    if not request.user.has_perm("vcs.update", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("All repositories were updated."),
        obj.do_update,
        request,
        method=request.GET.get("method"),
    )


def perform_push(request, obj):
    """Helper function to do the repository push."""
    if not request.user.has_perm("vcs.push", obj):
        raise PermissionDenied

    return execute_locked(
        request, obj, gettext("All repositories were pushed."), obj.do_push, request
    )


def perform_reset(request, obj):
    """Helper function to do the repository reset."""
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("All repositories have been reset."),
        obj.do_reset,
        request,
    )


def perform_cleanup(request, obj):
    """Helper function to do the repository cleanup."""
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("All repositories have been cleaned up."),
        obj.do_cleanup,
        request,
    )


def perform_file_sync(request, obj):
    """Helper function to do the repository file_sync."""
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("Translation files have been synchronized."),
        obj.do_file_sync,
        request,
    )


def perform_file_scan(request, obj):
    """Helper function to do the repository file_scan."""
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("Translations have been updated."),
        obj.do_file_scan,
        request,
    )


@login_required
@require_POST
def commit_project(request, project):
    obj = get_project(request, project)
    return perform_commit(request, obj)


@login_required
@require_POST
def commit_component(request, project, component):
    obj = get_component(request, project, component)
    return perform_commit(request, obj)


@login_required
@require_POST
def commit_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    return perform_commit(request, obj)


@login_required
@require_POST
def update_project(request, project):
    obj = get_project(request, project)
    return perform_update(request, obj)


@login_required
@require_POST
def update_component(request, project, component):
    obj = get_component(request, project, component)
    return perform_update(request, obj)


@login_required
@require_POST
def update_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    return perform_update(request, obj)


@login_required
@require_POST
def push_project(request, project):
    obj = get_project(request, project)
    return perform_push(request, obj)


@login_required
@require_POST
def push_component(request, project, component):
    obj = get_component(request, project, component)
    return perform_push(request, obj)


@login_required
@require_POST
def push_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    return perform_push(request, obj)


@login_required
@require_POST
def reset_project(request, project):
    obj = get_project(request, project)
    return perform_reset(request, obj)


@login_required
@require_POST
def reset_component(request, project, component):
    obj = get_component(request, project, component)
    return perform_reset(request, obj)


@login_required
@require_POST
def reset_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    return perform_reset(request, obj)


@login_required
@require_POST
def cleanup_project(request, project):
    obj = get_project(request, project)
    return perform_cleanup(request, obj)


@login_required
@require_POST
def cleanup_component(request, project, component):
    obj = get_component(request, project, component)
    return perform_cleanup(request, obj)


@login_required
@require_POST
def cleanup_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    return perform_cleanup(request, obj)


@login_required
@require_POST
def file_sync_project(request, project):
    obj = get_project(request, project)
    return perform_file_sync(request, obj)


@login_required
@require_POST
def file_sync_component(request, project, component):
    obj = get_component(request, project, component)
    return perform_file_sync(request, obj)


@login_required
@require_POST
def file_sync_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    return perform_file_sync(request, obj)


@login_required
@require_POST
def file_scan_project(request, project):
    obj = get_project(request, project)
    return perform_file_scan(request, obj)


@login_required
@require_POST
def file_scan_component(request, project, component):
    obj = get_component(request, project, component)
    return perform_file_scan(request, obj)


@login_required
@require_POST
def file_scan_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)
    return perform_file_scan(request, obj)
