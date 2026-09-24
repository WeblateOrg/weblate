# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext

from weblate.auth.permissions import get_project_repository_selection
from weblate.trans.models import Component, Project, Translation
from weblate.trans.repository import (
    RepositoryOperation,
    RepositoryOperationConflictError,
    can_access_repository_operation_task,
    get_repository_components,
    queue_repository_operation,
    reserve_repository_operation,
)
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


def execute_locked(
    request: AuthenticatedHttpRequest,
    obj,
    operation: RepositoryOperation,
    message,
    call,
    *args,
    **kwargs,
):
    """Wrap function call and gracefully handle possible lock exception."""
    repositories, _display_components = get_repository_components(obj)
    try:
        with (
            reserve_repository_operation(
                [component.pk for component in repositories], operation
            ) as release_reservation,
            transaction.atomic(),
        ):
            transaction.on_commit(release_reservation)
            result = call(*args, **kwargs)
            # With False the call is supposed to show errors on its own
            if result is None or result:
                messages.success(request, message)
    except RepositoryOperationConflictError:
        messages.error(
            request,
            gettext("Another repository operation is already in progress."),
        )
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


def queue_operation(
    request: AuthenticatedHttpRequest,
    obj: Project | Component | Translation,
    operation: RepositoryOperation,
    *,
    repo_components: tuple[Component, ...] | None = None,
) -> HttpResponseBase:
    """Queue a repository operation and redirect to its progress page."""
    try:
        queued = queue_repository_operation(
            obj,
            operation,
            request.user,
            repository_components=repo_components,
        )
    except RepositoryOperationConflictError as error:
        messages.error(
            request,
            gettext("Another repository operation is already in progress."),
        )
        if error.task_id and can_access_repository_operation_task(
            request.user, error.task_id
        ):
            return redirect(
                f"{reverse('show_progress', kwargs={'path': obj.get_url_path()})}?info=1"
            )
        return redirect_param(obj, "#repository")

    if queued.successful is False:
        messages.error(request, gettext("Repository operation completed with errors."))
        return redirect_param(obj, "#repository")

    if queued.reused:
        messages.info(request, gettext("This repository operation is already queued."))
    else:
        messages.success(request, gettext("Repository operation has been queued."))
    return redirect(
        f"{reverse('show_progress', kwargs={'path': obj.get_url_path()})}?info=1"
    )


def get_project_repository_kwargs(
    request: AuthenticatedHttpRequest, obj, permission: str
) -> dict[str, tuple[Component, ...]]:
    """Return the permitted project repository scope for an operation."""
    if not request.user.has_perm(permission, obj):
        raise PermissionDenied
    if not isinstance(obj, Project):
        return {}
    repositories = get_project_repository_selection(
        request.user, obj, (permission,)
    ).repositories
    if not repositories:
        raise PermissionDenied
    return {"repo_components": repositories}


@login_required
@require_repository_action_post
def update(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    repository_kwargs = get_project_repository_kwargs(request, obj, "vcs.update")

    method = request.GET.get("method")
    operation: RepositoryOperation = "pull"
    if method == "rebase":
        operation = "pull-rebase"
    elif method == "merge":
        operation = "pull-merge"
    elif method == "merge_noff":
        operation = "pull-merge-noff"
    return queue_operation(request, obj, operation, **repository_kwargs)


@login_required
@require_repository_action_post
def push(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    repository_kwargs = get_project_repository_kwargs(request, obj, "vcs.push")

    return queue_operation(request, obj, "push", **repository_kwargs)


@login_required
@require_repository_action_post
def reset(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    repository_kwargs = get_project_repository_kwargs(request, obj, "vcs.reset")

    operation: RepositoryOperation = (
        "reset-keep" if "keep_changes" in request.POST else "reset"
    )
    return queue_operation(request, obj, operation, **repository_kwargs)


@login_required
@require_repository_action_post
def cleanup(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    repository_kwargs = get_project_repository_kwargs(request, obj, "vcs.reset")

    return queue_operation(request, obj, "cleanup", **repository_kwargs)


@login_required
@require_repository_action_post
def file_sync(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    repository_kwargs = get_project_repository_kwargs(request, obj, "vcs.reset")

    return queue_operation(request, obj, "file-sync", **repository_kwargs)


@login_required
@require_repository_action_post
def file_scan(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    repository_kwargs = get_project_repository_kwargs(request, obj, "vcs.reset")

    return queue_operation(request, obj, "file-scan", **repository_kwargs)


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
        "remove-duplicates",
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
        "cleanup-unused",
        gettext("Unused strings have been removed from the translation file."),
        obj.do_cleanup_unused,
        request,
    )


@login_required
@require_repository_action_post
def remove_obsolete_units(
    request: AuthenticatedHttpRequest, path: list[str]
) -> HttpResponseBase:
    obj = parse_path(request, path, (Translation,))
    if not request.user.has_perm("vcs.reset", obj):
        raise PermissionDenied

    return execute_locked(
        request,
        obj,
        "remove-obsolete",
        gettext("Obsolete strings have been removed from the translation file."),
        obj.do_remove_obsolete_units,
        request,
    )


@login_required
@require_repository_action_post
def commit(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseBase:
    obj = parse_path(request, path, (Project, Component, Translation))
    repository_kwargs = get_project_repository_kwargs(request, obj, "vcs.commit")

    if isinstance(obj, Translation) and not obj.needs_commit():
        return redirect_param(obj, "#repository")
    return queue_operation(request, obj, "commit", **repository_kwargs)
