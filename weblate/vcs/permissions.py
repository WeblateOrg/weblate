# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.auth.results import PermissionResult


def managed_workspaces(user: User):
    """Return workspaces the user can manage."""
    return (
        Workspace.objects.filter(projects__in=user.managed_projects)
        | user.workspaces_with_perm("workspace.edit")
    ).distinct()


def user_can_migrate_to_github_app(user: User, workspace_id) -> bool:
    """
    Return whether the user may open the GitHub App migration for a workspace.

    Kept next to the queryset backing the view so that the alert offering the
    migration link never points at a workspace the user cannot manage.
    """
    if workspace_id is None:
        return False
    return managed_workspaces(user).filter(pk=workspace_id).exists()


def github_app_installation_workspaces(user: User):
    """Return workspaces where the user can connect GitHub accounts."""
    if user.has_perm("management.use"):
        return Workspace.objects.order()
    return user.workspaces_with_perm("workspace.edit")


def user_can_install_github_app_in_workspace(
    user: User, workspace: Workspace
) -> PermissionResult | bool:
    return user.has_perm("management.use") or user.has_perm("workspace.edit", workspace)
