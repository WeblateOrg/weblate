# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext

from weblate.trans.models import Component, Project, Translation
from weblate.trans.util import redirect_param
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from django.http import HttpResponseBase

    from weblate.auth.models import AuthenticatedHttpRequest


RepositoryActionView = Callable[
    ["AuthenticatedHttpRequest", list[str]], "HttpResponseBase"
]


def require_repository_action_post(
    function: RepositoryActionView,
) -> RepositoryActionView:
    @wraps(function)
    def wrapper(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
        if request.method == "POST":
            return function(request, path)
        obj = parse_path(request, path, (Project, Component, Translation))
        messages.error(
            request,
            gettext("Use the button on the repository status page to run this action."),
        )
        return redirect_param(obj, "#repository")

    return wrapper


@transaction.atomic
def execute_locked(
    request: AuthenticatedHttpRequest, obj, message, call, *args, **kwargs
):
    """Wrap function call and gracefully handle possible lock exception."""
    try:
        result = call(*args, **kwargs)
        # With False the call is supposed to show errors on its own
        if result is None or result:
            messages.success(request, message)
    except WeblateLockTimeoutError:
        messages.error(
            request,
            gettext(
                "There appears to be an ongoing operation on the repository. Please try again later."
            ),
        )
        if isinstance(obj, Project):
            report_error("Repository lock timeout", project=obj)
        elif isinstance(obj, Component):
            report_error("Repository lock timeout", project=obj.project)
        else:
            report_error("Repository lock timeout", project=obj.component.project)

    return redirect_param(obj, "#repository")


def queue_commit(request: AuthenticatedHttpRequest, obj) -> bool:
    """Queue commit operation for browser requests."""
    user_id = request.user.id
    if isinstance(obj, Project):
        for component in obj.all_repo_components:
            component.queue_commit_pending("commit", user_id=user_id)
    elif isinstance(obj, Translation):
        if not obj.needs_commit():
            return False
        obj.component.queue_commit_pending("commit", user_id=user_id)
    else:
        obj.queue_commit_pending("commit", user_id=user_id)
    return True


@login_required
@require_repository_action_post
def update(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("vcs.update", obj):
        raise PermissionDenied

    result = execute_locked(
        request,
        obj,
        gettext(
            "All repositories have been updated, updates of translations are in progress."
        ),
        obj.do_update,
        request,
        method=request.GET.get("method"),
    )
    if result:
        return redirect(
            f"{reverse('show_progress', kwargs={'path': obj.get_url_path()})}?info=1"
        )
    return result


@login_required
@require_repository_action_post
def push(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("vcs.push", obj):
        raise PermissionDenied

    return execute_locked(
        request, obj, gettext("All repositories were pushed."), obj.do_push, request
    )


@login_required
@require_repository_action_post
def reset(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    result = execute_locked(
        request,
        obj,
        gettext(
            "All repositories have been reset, updates of translations are in progress."
        ),
        obj.do_reset,
        request,
        keep_changes="keep_changes" in request.POST,
    )
    if result:
        return redirect(
            f"{reverse('show_progress', kwargs={'path': obj.get_url_path()})}?info=1"
        )
    return result


@login_required
@require_repository_action_post
def cleanup(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
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
@require_repository_action_post
def file_sync(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
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
@require_repository_action_post
def file_scan(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    result = execute_locked(
        request,
        obj,
        gettext("Updates of translations are in progress."),
        obj.do_file_scan,
        request,
    )
    if result:
        return redirect(
            f"{reverse('show_progress', kwargs={'path': obj.get_url_path()})}?info=1"
        )
    return result


@login_required
@require_repository_action_post
def remove_duplicate_units(
    request: AuthenticatedHttpRequest, path: list[str]
) -> HttpResponseBase:
    obj = parse_path(request, path, (Translation,))
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("Duplicate strings have been removed from the translation file."),
        obj.do_remove_duplicate_units,
        request,
    )


@login_required
@require_repository_action_post
def cleanup_unused(
    request: AuthenticatedHttpRequest, path: list[str]
) -> HttpResponseBase:
    obj = parse_path(request, path, (Translation,))
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        gettext("Unused strings have been removed from the translation file."),
        obj.do_cleanup_unused,
        request,
    )


@login_required
@require_repository_action_post
def commit(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("vcs.commit", obj):
        raise PermissionDenied

    if not settings.CELERY_TASK_ALWAYS_EAGER:
        result = queue_commit(request, obj)
        if result:
            messages.success(
                request, gettext("Pending translations are being committed.")
            )
        return redirect_param(obj, "#repository")

    return execute_locked(
        request,
        obj,
        gettext("All pending translations were committed."),
        obj.commit_pending,
        "commit",
        request.user,
    )
