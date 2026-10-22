# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Database locks for cross-component quality checks."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING

from django.db import connection, transaction

from weblate.trans.propagation import get_propagation_scope

if TYPE_CHECKING:
    from collections.abc import Generator
    from uuid import UUID

    from weblate.trans.models import Component, Project


def lock_check_workspaces(workspace_ids: set[UUID], *, exclusive: bool) -> None:
    """Guard workspace membership and policy before taking project locks."""
    if not connection.in_atomic_block:
        msg = "Check workspace locks require a database transaction"
        raise RuntimeError(msg)
    statement = (
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
        if exclusive
        else "SELECT pg_advisory_xact_lock_shared(hashtextextended(%s, 0))"
    )
    with connection.cursor() as cursor:
        for workspace_id in sorted(workspace_ids):
            cursor.execute(statement, [f"weblate-workspace-checks:{workspace_id}"])


def lock_check_projects(
    project_ids: set[int], *, exclusive: bool, workspace_ids: set[UUID] | None = None
) -> None:
    """Lock workspaces before projects and retry if membership changed while waiting."""
    if not connection.in_atomic_block:
        msg = "Check project locks require a database transaction"
        raise RuntimeError(msg)
    from weblate.trans.models import Project  # ruff: ignore[import-outside-top-level]

    projects = Project.objects.filter(pk__in=project_ids)
    statement = (
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
        if exclusive
        else "SELECT pg_advisory_xact_lock_shared(hashtextextended(%s, 0))"
    )
    while True:
        membership = dict(projects.values_list("pk", "workspace_id"))
        with transaction.atomic():
            lock_check_workspaces(
                {value for value in membership.values() if value is not None}
                | (workspace_ids or set()),
                exclusive=exclusive,
            )
            with connection.cursor() as cursor:
                for project_id in sorted(project_ids):
                    cursor.execute(statement, [f"weblate-checks:{project_id}"])
            if membership == dict(projects.values_list("pk", "workspace_id")):
                return
            # A move committed while we waited. Release the previous locks and
            # acquire the new workspace set in the same deterministic order.
            transaction.set_rollback(True)


@contextmanager
def check_project_session_read_lock(project_id: int) -> Generator[None, None, None]:
    """Hold a shared lock across a worker's chunked database transactions."""
    from weblate.trans.models import Project  # ruff: ignore[import-outside-top-level]

    while True:
        workspace_id = (
            Project.objects.filter(pk=project_id)
            .values_list("workspace_id", flat=True)
            .first()
        )
        keys = [f"weblate-checks:{project_id}"]
        if workspace_id is not None:
            keys.insert(0, f"weblate-workspace-checks:{workspace_id}")
        with ExitStack() as stack:
            for key in keys:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_lock_shared(hashtextextended(%s, 0))", [key]
                    )
                stack.callback(_unlock_check_session, key)
            if (
                workspace_id
                != Project.objects.filter(pk=project_id)
                .values_list("workspace_id", flat=True)
                .first()
            ):
                continue
            yield
            return


def _unlock_check_session(key: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_unlock_shared(hashtextextended(%s, 0))", [key]
        )


def _project_check_boundary(project: Project) -> tuple[int, UUID | None, str, int]:
    return (
        project.pk,
        project.workspace_id,
        get_propagation_scope(project),
        project.access_control,
    )


def _refresh_check_component(component: Component, current: Component) -> None:
    # Keep shared project instances connected when only component settings were
    # refreshed. Replacing them unconditionally leaves later settings edits on
    # a different instance from the one used by this component.
    if _project_check_boundary(component.project) != _project_check_boundary(
        current.project
    ):
        component.project = current.project
    component.name = current.name
    component.restricted = current.restricted
    component.allow_translation_propagation = current.allow_translation_propagation


@contextmanager
def check_project_read_lock(component: Component) -> Generator[bool, None, None]:
    """Refresh component access after waiting for a boundary transition."""
    from weblate.trans.models import Component, Project  # ruff: ignore[import-outside-top-level]

    with transaction.atomic():
        previous = (
            component.project_id,
            component.name,
            component.project.workspace_id,
            get_propagation_scope(component.project),
            component.project.access_control,
            component.restricted,
            component.allow_translation_propagation,
        )
        project_id = component.project_id
        while True:
            workspace_id = Project.objects.values_list("workspace_id", flat=True).get(
                pk=project_id
            )
            with transaction.atomic():
                lock_check_projects({project_id}, exclusive=False)
                current = Component.objects.select_related("project__workspace").get(
                    pk=component.pk
                )
                moved = (
                    current.project_id != project_id
                    or current.project.workspace_id != workspace_id
                )
                if moved:
                    # Rolling back this savepoint releases the old project's lock.
                    transaction.set_rollback(True)
            if moved:
                project_id = current.project_id
                continue
            _refresh_check_component(component, current)
            break
        yield previous != (
            component.project_id,
            component.name,
            component.project.workspace_id,
            get_propagation_scope(component.project),
            component.project.access_control,
            component.restricted,
            component.allow_translation_propagation,
        )


@contextmanager
def check_component_session_read_lock(
    component: Component,
) -> Generator[None, None, None]:
    """Keep a batch check on one boundary across its chunked writes."""
    from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

    project_id = component.project_id
    while True:
        with check_project_session_read_lock(project_id):
            current = Component.objects.select_related("project__workspace").get(
                pk=component.pk
            )
            if current.project_id == project_id:
                _refresh_check_component(component, current)
                yield
                return
        project_id = current.project_id
