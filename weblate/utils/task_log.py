# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Capture task diagnostics together with their visibility requirements."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from django.core.cache import cache

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.auth.models import User
    from weblate.trans.models import Component


class TaskLogEntry(TypedDict):
    component_id: int
    message: str
    suffix: str
    sensitive: bool
    required_component_ids: list[int]
    repository_ids: list[int]


def get_log_user_label(user: User) -> str:
    if "@" in user.username:
        return f"<User:{user.pk}>" if user.pk else "<User>"
    return user.username


def make_task_log_entry(
    component: Component,
    message: str,
    *,
    sensitive: bool = False,
    suffix: str = "",
    dependencies: Iterable[Component] = (),
) -> TaskLogEntry:
    sources = [component, *dependencies]
    owners = {
        source.effective_repo_component.pk: source.effective_repo_component
        for source in sources
    }
    if sensitive:
        from weblate.trans.util import sanitize_backend_error_message  # ruff: ignore[import-outside-top-level]

        message = sanitize_backend_error_message(
            message,
            repo_urls=[
                url
                for source in [*sources, *owners.values()]
                for url in (source.repo, source.push)
            ],
            extra_paths=[source.full_path for source in [*sources, *owners.values()]],
        )
    return {
        "component_id": component.pk,
        "message": message,
        "suffix": suffix,
        "sensitive": sensitive,
        "required_component_ids": sorted(
            {source.pk for source in sources} | set(owners)
        ),
        "repository_ids": sorted(owners),
    }


def append_task_logs(task_id: str, new_entries: Iterable[TaskLogEntry]) -> None:
    from weblate.utils.celery import TASK_METADATA_TTL  # ruff: ignore[import-outside-top-level]

    batch = list(new_entries)
    if not batch:
        return
    key = f"task-log-{task_id}"
    entries = cache.get(key, [])
    entries.extend(batch)
    cache.set(key, entries, TASK_METADATA_TTL)


def append_task_log(task_id: str, entry: TaskLogEntry) -> None:
    append_task_logs(task_id, [entry])


def is_task_log_entry(entry: object) -> bool:
    """Fail closed for old formats or incomplete provenance."""
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("component_id"), int)
        and isinstance(entry.get("message"), str)
        and isinstance(entry.get("suffix"), str)
        and isinstance(entry.get("sensitive"), bool)
        and all(
            isinstance(entry.get(key), list)
            and bool(entry[key])
            and all(isinstance(value, int) for value in entry[key])
            for key in ("required_component_ids", "repository_ids")
        )
    )


def get_visible_user_task_log(task_id: str, user: User) -> list[str]:
    return [
        entry["message"]
        for entry in cache.get(f"task-user-log-{task_id}", [])
        if isinstance(entry, dict)
        and isinstance(entry.get("user_id"), int)
        and entry["user_id"] == user.pk
        and isinstance(entry.get("message"), str)
    ]


def record_user_task_failure(task_id: str, exception: object) -> None:
    from weblate.trans.util import sanitize_backend_error_message  # ruff: ignore[import-outside-top-level]
    from weblate.utils.celery import TASK_METADATA_TTL, get_task_metadata  # ruff: ignore[import-outside-top-level]

    metadata = get_task_metadata(task_id) or {}
    if (
        metadata.get("task_kind") != "automatic-translation"
        or not isinstance(metadata.get("user_id"), int)
        or any(
            metadata.get(key)
            for key in ("component_id", "component_ids", "translation_id")
        )
    ):
        return
    key = f"task-user-log-{task_id}"
    entries = cache.get(key, [])
    entries.append(
        {
            "user_id": metadata["user_id"],
            "message": sanitize_backend_error_message(str(exception)),
        }
    )
    cache.set(key, entries, TASK_METADATA_TTL)


def get_visible_task_log(task_id: str, user: User) -> list[str]:
    from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

    entries: list[TaskLogEntry] = [
        entry
        for entry in cache.get(f"task-log-{task_id}", [])
        if is_task_log_entry(entry)
    ]
    ids = {entry["component_id"] for entry in entries}
    for entry in entries:
        if entry["sensitive"]:
            ids.update(entry["required_component_ids"])
            ids.update(entry["repository_ids"])
    if not ids:
        return get_visible_user_task_log(task_id, user)
    components = {
        component.pk: component
        for component in Component.objects.filter_access(user)
        .filter(pk__in=ids)
        .prefetch(alerts=False)
    }
    permissions: dict[int, bool] = {}
    result = []
    for entry in entries:
        component = components.get(entry["component_id"])
        if component is None:
            continue
        if entry["sensitive"]:
            if not set(entry["required_component_ids"]).issubset(components) or not set(
                entry["repository_ids"]
            ).issubset(components):
                continue
            for pk in entry["repository_ids"]:
                if pk not in permissions:
                    permissions[pk] = bool(user.has_perm("vcs.view", components[pk]))
            if not all(permissions[pk] for pk in entry["repository_ids"]):
                continue
        result.append(f"{component.full_slug}{entry['suffix']}: {entry['message']}")
    return result + get_visible_user_task_log(task_id, user)


def get_task_components(task_id: str) -> list[Component]:
    from weblate.trans.models import Component, Translation  # ruff: ignore[import-outside-top-level]
    from weblate.utils.celery import get_task_metadata  # ruff: ignore[import-outside-top-level]

    metadata = get_task_metadata(task_id) or {}
    ids = set(metadata.get("component_ids") or ())
    if component_id := metadata.get("component_id"):
        ids.add(component_id)
    if translation_id := metadata.get("translation_id"):
        ids.update(
            Translation.objects.filter(pk=translation_id).values_list(
                "component_id", flat=True
            )
        )
    return list(Component.objects.filter(pk__in=ids).prefetch(alerts=False))


def record_repository_failure(
    task_id: str,
    component: Component,
    operation: str,
    *,
    sources: list[Component] | None = None,
) -> None:
    """Identify a failed repository through its task's display components."""
    if sources is None:
        sources = get_task_components(task_id)
    append_task_logs(
        task_id,
        (
            make_task_log_entry(source, f"Repository {operation} failed.")
            for source in sources or [component]
            if component.pk in {source.pk, source.linked_component_id}
        ),
    )


def record_repository_progress(
    task_id: str,
    component: Component,
    operation: str,
    state: str,
    *,
    sources: list[Component],
) -> None:
    """Expose static summaries through the task's display components."""
    append_task_logs(
        task_id,
        (
            make_task_log_entry(source, f"Repository {operation} {state}.")
            for source in sources or [component]
        ),
    )


def record_task_failure(task_id: str, exception: object) -> None:
    components = get_task_components(task_id)
    if not components:
        record_user_task_failure(task_id, exception)
        return
    append_task_logs(
        task_id,
        [
            make_task_log_entry(component, "Task could not be completed.")
            for component in components
        ]
        + [
            make_task_log_entry(
                components[0],
                str(exception),
                sensitive=True,
                dependencies=components[1:],
            )
        ],
    )
