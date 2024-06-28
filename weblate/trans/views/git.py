# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from weblate.trans.models import Component, Project, Translation
from weblate.trans.util import redirect_param
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.views import parse_path


def execute_locked(request, obj, message, call, *args, **kwargs):
    """Wrap function call and gracefully handle possible lock exception."""
    try:
        result = call(*args, **kwargs)
        # With False the call is supposed to show errors on its own
        if result is None or result:
            messages.success(request, message)
    except WeblateLockTimeoutError:
        messages.error(
            request,
            gettext("Could not lock the repository, another operation is in progress."),
        )
        if isinstance(obj, Project):
            report_error(project=obj)
        elif isinstance(obj, Component):
            report_error(project=obj.project)
        else:
            report_error(project=obj.component.project)

    return redirect_param(obj, "#repository")


@login_required
@require_POST
def update(request, path):
    obj = parse_path(request, path, (Project, Component, Translation))
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


@login_required
@require_POST
def push(request, path):
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("vcs.push", obj):
        raise PermissionDenied

    return execute_locked(
        request, obj, gettext("All repositories were pushed."), obj.do_push, request
    )


@login_required
@require_POST
def reset(request, path):
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("All repositories have been reset."),
        obj.do_reset,
        request,
    )


@login_required
@require_POST
def cleanup(request, path):
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("All repositories have been cleaned up."),
        obj.do_cleanup,
        request,
    )


@login_required
@require_POST
def file_sync(request, path):
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("Translation files have been synchronized."),
        obj.do_file_sync,
        request,
    )


@login_required
@require_POST
def file_scan(request, path):
    obj = parse_path(request, path, (Project, Component, Translation))
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
def commit(request, path):
    obj = parse_path(request, path, (Project, Component, Translation))
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
