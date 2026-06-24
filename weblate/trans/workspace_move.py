# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import User
    from weblate.trans.models import Project
    from weblate.workspaces.models import Workspace

PROJECT_MOVE_WORKSPACE_SELECT_LIMIT = 100


def get_project_move_target_workspaces(
    user: User, project: Project
) -> QuerySet[Workspace, Workspace]:
    """Return workspaces the user can move a project into."""
    return (
        user.workspaces_with_perm("workspace.edit")
        .filter(pk__in=user.workspaces_with_perm("workspace.add_project").values("pk"))
        .exclude(pk=project.workspace_id)
    )


def can_offer_project_move(user: User, project: Project) -> bool:
    """Return whether the project move form can offer at least one move."""
    if not user.has_perm("project.edit", project):
        return False
    if project.workspace_id is not None and not user.has_perm(
        "workspace.edit", project.workspace
    ):
        return False
    if project.workspace_id is not None and user.has_perm("project.add"):
        return True
    return get_project_move_target_workspaces(user, project).exists()


def get_project_move_billing_error(workspace: Workspace | None) -> StrOrPromise | None:
    """Return billing validation error for a move target."""
    if workspace is None or "weblate.billing" not in settings.INSTALLED_APPS:
        return None

    billing = None
    with suppress(AttributeError, ObjectDoesNotExist):
        billing = workspace.billing
    if billing is None:
        return None

    # ruff: ignore[import-outside-top-level]
    from weblate.billing.models import Billing

    billings = Billing.objects.filter(pk=billing.pk).get_valid().prefetch()
    for candidate in billings:
        limit = candidate.plan.display_limit_projects
        if limit == 0 or candidate.count_projects < limit:
            return None
    return gettext("No valid billing found or limit exceeded.")


def get_project_workspace_move_permission_error(
    user: User,
    project: Project,
    workspace: Workspace | None,
    *,
    reject_unchanged: bool = False,
) -> StrOrPromise | None:
    """Return a permission error for moving project to workspace."""
    workspace_id = workspace.pk if workspace else None
    if workspace_id == project.workspace_id:
        if reject_unchanged:
            return gettext("The project is already assigned to this workspace.")
        return None

    if project.workspace_id is not None and not user.has_perm(
        "workspace.edit", project.workspace
    ):
        return gettext("You do not have permission to edit the current workspace.")

    if workspace is None:
        if not user.has_perm("project.add"):
            return gettext(
                "You do not have permission to move projects without a workspace."
            )
        return None

    if not user.has_perm("workspace.edit", workspace):
        return gettext("You do not have permission to edit the target workspace.")
    if not user.has_perm("workspace.add_project", workspace):
        return gettext(
            "You do not have permission to add projects to the target workspace."
        )

    return None


def get_project_workspace_move_error(
    user: User,
    project: Project,
    workspace: Workspace | None,
    *,
    reject_unchanged: bool = False,
) -> StrOrPromise | None:
    """Return a validation error for moving project to workspace."""
    if error := get_project_workspace_move_permission_error(
        user, project, workspace, reject_unchanged=reject_unchanged
    ):
        return error
    return get_project_move_billing_error(workspace)
