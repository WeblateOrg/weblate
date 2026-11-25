# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared translation propagation boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q

from weblate.utils.change_origin import capture_change_origin

if TYPE_CHECKING:
    from collections.abc import Callable

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


def _propagation_rebuild_key(
    project: Project, component_name: str | None
) -> tuple[int | str, str | None]:
    scope = get_propagation_scope(project)
    boundary = project.pk if scope == "project" else str(project.workspace_id)
    return boundary, component_name if scope == "component_name" else None


@dataclass
class PendingPropagationRebuild:
    project_id: int
    component_name: str | None
    published: set[tuple[int | str, str | None]]

    publish: Callable[[], None] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.publish = capture_change_origin(self._publish)

    def __call__(self) -> None:
        self.publish()

    def _publish(self) -> None:
        from weblate.checks.models import CHECKS  # ruff: ignore[import-outside-top-level]
        from weblate.checks.tasks import finalize_component_checks  # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Component, Project  # ruff: ignore[import-outside-top-level]

        project = (
            Project.objects.select_related("workspace")
            .filter(pk=self.project_id)
            .first()
        )
        if project is None:
            return
        key = _propagation_rebuild_key(project, self.component_name)
        if key in self.published:
            return
        component = (
            Component.objects.filter(
                propagation_filter(project, "", self.component_name),
                allow_translation_propagation=True,
            )
            .order_by("pk")
            .first()
        )
        enabled = [name for name in ("inconsistent", "reused") if name in CHECKS]
        if component is not None and enabled:
            finalize_component_checks.delay(component.pk, [], enabled, batch_mode=True)
            self.published.add(key)


def schedule_propagation_rebuild(project: Project, component_name: str | None) -> None:
    # Share only the set of successful publications. Savepoint rollback can
    # discard any callback without losing work registered by another callback.
    published = next(
        (
            callback.published
            for _, callback, _ in transaction.get_connection().run_on_commit
            if isinstance(callback, PendingPropagationRebuild)
        ),
        set(),
    )
    transaction.on_commit(
        PendingPropagationRebuild(project.pk, component_name, published)
    )


def refresh_propagation_checks(
    project_ids: set[int], *, component_name: str | None = None
) -> None:
    """Remove inaccessible warnings now and rebuild affected groups after commit."""
    # ruff: ignore[import-outside-top-level]
    from weblate.checks.consistency import stale_project_check_units
    from weblate.checks.models import CHECKS, Check  # ruff: ignore[import-outside-top-level]
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
            if component_name is not None:
                stale = stale.filter(unit__translation__component__name=component_name)
            if name in enabled:
                stale = stale.filter(
                    unit_id__in=stale_project_check_units(
                        project, name, component_name=component_name
                    ).values("pk")
                )
            affected.update(stale.values_list("unit__translation_id", flat=True))
            stale.delete()
    for translation in Translation.objects.filter(pk__in=affected):
        translation.invalidate_cache()
    if not enabled:
        return
    if component_name is not None:
        for project in projects:
            if project.pk in project_ids:
                schedule_propagation_rebuild(project, component_name)
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
        key = _propagation_rebuild_key(project, component.name)
        if key not in scheduled:
            scheduled.add(key)
            schedule_propagation_rebuild(project, key[1])
