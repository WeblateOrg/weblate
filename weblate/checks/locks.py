# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Database locks for cross-component quality checks."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from django.db import connection, transaction

if TYPE_CHECKING:
    from collections.abc import Generator

    from weblate.trans.models import Component


def lock_check_projects(project_ids: set[int], *, exclusive: bool) -> None:
    """Serialize access changes with readers which might write check rows."""
    if not connection.in_atomic_block:
        msg = "Check project locks require a database transaction"
        raise RuntimeError(msg)
    statement = (
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
        if exclusive
        else "SELECT pg_advisory_xact_lock_shared(hashtextextended(%s, 0))"
    )
    with connection.cursor() as cursor:
        for project_id in sorted(project_ids):
            cursor.execute(statement, [f"weblate-checks:{project_id}"])


@contextmanager
def check_project_session_read_lock(project_id: int) -> Generator[None, None, None]:
    """Hold a shared lock across a worker's chunked database transactions."""
    key = f"weblate-checks:{project_id}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock_shared(hashtextextended(%s, 0))", [key])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock_shared(hashtextextended(%s, 0))", [key]
            )


@contextmanager
def check_project_read_lock(component: Component) -> Generator[bool, None, None]:
    """Refresh component access after waiting for a boundary transition."""
    from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

    with transaction.atomic():
        previous = (
            component.project_id,
            component.restricted,
            component.allow_translation_propagation,
        )
        project_id = component.project_id
        while True:
            with transaction.atomic():
                lock_check_projects({project_id}, exclusive=False)
                current = Component.objects.only(
                    "project_id", "restricted", "allow_translation_propagation"
                ).get(pk=component.pk)
                moved = current.project_id != project_id
                if moved:
                    # Rolling back this savepoint releases the old project's lock.
                    transaction.set_rollback(True)
            if moved:
                project_id = current.project_id
                continue
            component.project_id = current.project_id
            component.restricted = current.restricted
            component.allow_translation_propagation = (
                current.allow_translation_propagation
            )
            break
        yield previous != (
            component.project_id,
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
            current = Component.objects.only(
                "project_id", "restricted", "allow_translation_propagation"
            ).get(pk=component.pk)
            if current.project_id == project_id:
                component.project_id = current.project_id
                component.restricted = current.restricted
                component.allow_translation_propagation = (
                    current.allow_translation_propagation
                )
                yield
                return
        project_id = current.project_id
