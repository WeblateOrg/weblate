# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings

from weblate.trans.models import Component, Project

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models.component import ComponentQuerySet
    from weblate.trans.models.project import ProjectQuerySet


def get_creation_projects(user: User) -> ProjectQuerySet:
    """Return projects available for component creation."""
    if user.is_superuser:
        return Project.objects.order()
    if "weblate.billing" in settings.INSTALLED_APPS:
        # ruff: ignore[import-outside-top-level]
        from weblate.billing.models import Billing

        return user.managed_projects.filter(
            workspace__billing__in=Billing.objects.get_valid()
        ).order()
    return user.managed_projects


def get_creation_components(
    user: User, projects: ProjectQuerySet, project_id: int | None = None
) -> ComponentQuerySet:
    """Return accessible repository components in creation projects."""
    components = (
        Component.objects.filter_access(user)
        .with_repo()
        .filter(project__in=projects)
        .order_project()
    )
    if project_id is not None:
        components = components.filter(project_id=project_id)
    return components


def get_component_branches(component: Component) -> list[str]:
    """Discover unused remote branches for one eligible component."""
    branches = component.repository.list_remote_branches(timeout=15)
    existing = set(
        Component.objects.filter(repo=component.repo).values_list("branch", flat=True)
    )
    return [
        branch
        for branch in branches
        if branch != component.branch and branch not in existing
    ]
