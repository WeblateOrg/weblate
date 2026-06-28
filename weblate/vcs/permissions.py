# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.auth.models import User


def github_app_installation_workspaces(user: User):
    """Return workspaces where the user can connect GitHub accounts."""
    if user.has_perm("management.use"):
        return Workspace.objects.order()
    return user.workspaces_with_perm("workspace.edit")


def user_can_install_github_app_in_workspace(user: User, workspace: Workspace) -> bool:
    return user.has_perm("management.use") or user.has_perm("workspace.edit", workspace)
