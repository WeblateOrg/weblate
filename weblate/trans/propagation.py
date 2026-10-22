# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared translation propagation boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

if TYPE_CHECKING:
    from django.db.models import OuterRef

    from weblate.trans.models import Project


def get_propagation_scope(project: Project) -> str:
    workspace = project.workspace
    return workspace.propagation_scope if workspace is not None else "project"


def workspace_propagation(project: Project) -> bool:
    return get_propagation_scope(project) != "project"


def propagation_filter(
    project: Project,
    prefix: str,
    component_name: str | OuterRef | None = None,
) -> Q:
    """Select a propagation boundary, optionally narrowed to one component name."""
    if not workspace_propagation(project):
        return Q(**{f"{prefix}project_id": project.pk})
    result = Q(**{f"{prefix}project__workspace_id": project.workspace_id})
    if (
        get_propagation_scope(project) == "component_name"
        and component_name is not None
    ):
        result &= Q(**{f"{prefix}name": component_name})
    return result


def propagation_uses_custom_sources(project: Project) -> bool:
    # A workspace can mix projects with and without translation parents. Always
    # resolve effective sources on both sides of a workspace comparison.
    return workspace_propagation(project) or bool(
        project.translation_parent_language_ids
    )


def refresh_propagation_checks(project_ids: set[int]) -> None:
    """Remove inaccessible warnings now and rebuild affected groups after commit."""
    # ruff: ignore[import-outside-top-level]
    from weblate.checks.consistency import stale_project_check_units
    from weblate.checks.models import CHECKS, Check  # ruff: ignore[import-outside-top-level]
    from weblate.checks.tasks import finalize_component_checks  # ruff: ignore[import-outside-top-level]
    from weblate.trans.models import Component, Project, Translation  # ruff: ignore[import-outside-top-level]

    workspaces = (
        Project.objects.filter(pk__in=project_ids)
        .exclude(workspace__isnull=True)
        .values("workspace_id")
    )
    projects = list(
        Project.objects.filter(Q(pk__in=project_ids) | Q(workspace_id__in=workspaces))
        .select_related("workspace")
        .order_by("pk")
    )
    affected: set[int] = set()
    enabled = [name for name in ("inconsistent", "reused") if name in CHECKS]
    for project in projects:
        for name in ("inconsistent", "reused"):
            stale = Check.objects.filter(
                name=name, unit__translation__component__project=project
            )
            if name in enabled:
                stale = stale.filter(
                    unit_id__in=stale_project_check_units(project, name).values("pk")
                )
            affected.update(stale.values_list("unit__translation_id", flat=True))
            stale.delete()
    for translation in Translation.objects.filter(pk__in=affected):
        translation.invalidate_cache()
    if not enabled:
        return
    scheduled = set()
    for component in (
        Component.objects.filter(
            project__in=projects, allow_translation_propagation=True
        )
        .select_related("project__workspace")
        .order_by("pk")
    ):
        project = component.project
        key = (
            (project.workspace_id, component.name)
            if workspace_propagation(project)
            and get_propagation_scope(project) == "component_name"
            else (project.workspace_id, None)
            if workspace_propagation(project)
            else (project.pk, None)
        )
        if key not in scheduled:
            scheduled.add(key)
            finalize_component_checks.delay_on_commit(
                component.pk, [], enabled, batch_mode=True
            )
