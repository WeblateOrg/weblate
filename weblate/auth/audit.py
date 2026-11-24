# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Explicit audit boundaries for team administration."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

from django.db import router, transaction

from weblate.accounts.models import AuditLog, TeamAuditLog
from weblate.auth.models import Group, User
from weblate.trans.models.project import Project
from weblate.utils.change_origin import get_acting_user

if TYPE_CHECKING:
    from collections.abc import Generator

    from django.http import HttpRequest
    from rest_framework.request import Request

    from weblate.auth.models import AuthenticatedHttpRequest

_audited_teams: ContextVar[frozenset[int]] = ContextVar(
    "audited_teams", default=frozenset()
)


def audit_actor(
    request: HttpRequest | Request | None, actor: User | None = None
) -> User | None:
    """Resolve the supplied initiating actor or the current operation actor."""
    if actor is not None:
        return actor
    request_user = getattr(request, "user", None)
    if isinstance(request_user, User):
        return request_user
    return get_acting_user()


def team_state(team: Group) -> dict[str, Any] | None:
    """Read persisted state, independent of a model form's mutated instance."""
    if team.pk is None:
        return None
    current = (
        Group.objects.using(router.db_for_write(Group, instance=team))
        .select_related("defining_project", "defining_workspace")
        .filter(pk=team.pk)
        .first()
    )
    if current is None:
        return None
    project = current.defining_project
    workspace = current.defining_workspace
    components: list[dict[str, Any]] = [
        dict(value)
        for value in current.components.order_by("pk").values(
            "id", "project_id", "project__slug", "slug", "category_id"
        )
    ]
    projects: list[dict[str, Any]] = [
        dict(value) for value in current.projects.order_by("pk").values("id", "slug")
    ]
    componentlists: list[dict[str, Any]] = [
        dict(value)
        for value in current.componentlists.order_by("pk").values("id", "slug")
    ]
    if project is not None or workspace is not None:
        # Historical stale assignments must not reveal another tenant's names.
        components = [
            value
            if project is not None and value["project_id"] == project.pk
            else {"id": value["id"], "unavailable": True}
            for value in components
        ]
        projects = [
            value
            if project is not None and value["id"] == project.pk
            else {"id": value["id"], "unavailable": True}
            for value in projects
        ]
        componentlists = [
            {"id": value["id"], "unavailable": True} for value in componentlists
        ]
    return {
        "name": current.name,
        "project_id": current.defining_project_id,
        "project_slug": project.slug if project is not None else "",
        "workspace_name": workspace.name if workspace is not None else "",
        "workspace_id": str(current.defining_workspace_id)
        if current.defining_workspace_id
        else None,
        "project_selection": current.project_selection,
        "language_selection": current.language_selection,
        "enforced_2fa": current.enforced_2fa,
        "internal": current.internal,
        "roles": list(current.roles.order_by("pk").values("id", "name")),
        "projects": projects,
        "components": components,
        "componentlists": componentlists,
        "languages": list(current.languages.order_by("pk").values("id", "code")),
        "admins": list(current.admins.order_by("pk").values("id", "username")),
        "automatic_rules": list(
            current.autogroup_set.order_by("pk").values_list("match", flat=True)
        ),
    }


def record_team_event(
    team: Group,
    actor: User,
    event: str,
    details: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
) -> None:
    """Write only to the permission-restricted log, preserving deleted scopes."""
    if state is None:
        project = team.defining_project
        workspace = team.defining_workspace
        scope: dict[str, Any] = {
            "name": team.name,
            "project_id": team.defining_project_id,
            "project_slug": project.slug if project is not None else "",
            "workspace_name": workspace.name if workspace is not None else "",
            "workspace_id": team.defining_workspace_id,
        }
    else:
        scope = state
    TeamAuditLog.objects.using(router.db_for_write(Group, instance=team)).create(
        team_id=team.pk,
        team_name=scope["name"],
        scope="project"
        if scope["project_id"]
        else ("workspace" if scope["workspace_id"] else "site"),
        scope_label=scope["project_slug"] or scope["workspace_name"],
        project_id=scope["project_id"],
        workspace_id=scope["workspace_id"],
        actor=actor,
        event=event,
        details=details,
    )


def membership_limits(user: User) -> dict[int, list[str]]:
    """Snapshot per-member limits without loading whole team memberships."""
    if user.pk is None:
        return {}
    return {
        membership.group_id: sorted(
            language.code for language in membership.limit_languages.all()
        )
        for membership in user.team_memberships.prefetch_related("limit_languages")
    }


def audit_membership_limits(
    user: User,
    before: dict[int, list[str]],
    actor: User,
    request: AuthenticatedHttpRequest,
) -> None:
    """Record changes made by Django admin's membership inline."""
    memberships = user.team_memberships.select_related(
        "group__defining_project", "group__defining_workspace"
    ).prefetch_related("limit_languages")
    for membership in memberships:
        languages = sorted(
            language.code for language in membership.limit_languages.all()
        )
        previous = before.get(membership.group_id, [])
        if languages == previous:
            continue
        if membership.group_id in before:
            user.audit_team_access_change(
                request,
                membership.group,
                actor=actor,
                previous_limit_languages=previous,
                limit_languages=languages,
            )
        else:
            record_team_event(
                membership.group,
                actor,
                TeamAuditLog.Event.MEMBER_CHANGED,
                {
                    "username": user.username,
                    "previous_limit_languages": previous,
                    "limit_languages": languages,
                },
            )


def record_admin_change(
    team: Group,
    user_id: int,
    actor: User,
    *,
    granted: bool,
    request: HttpRequest | Request | None = None,
) -> None:
    """Audit administrator grants and revocations on the affected account."""
    user = (
        User.objects.using(router.db_for_write(Group, instance=team))
        .filter(pk=user_id)
        .first()
    )
    if user is not None:
        AuditLog.objects.db_manager(router.db_for_write(Group, instance=team)).create(
            user=user,
            request=cast("HttpRequest | None", getattr(request, "_request", request)),
            actor=actor,
            activity="team-admin-added" if granted else "team-admin-removed",
            team=team.name,
            username=actor.username,
        )


def log_team_changes(
    team: Group,
    before: dict[str, Any] | None,
    actor: User,
    request: HttpRequest | Request | None = None,
) -> None:
    """Record definition deltas and the affected administrator accounts."""
    after = team_state(team)
    if before == after:
        return
    if (
        before is not None
        and after is not None
        and (before["project_id"], before["workspace_id"])
        != (after["project_id"], after["workspace_id"])
    ):
        # Never expose a former scope's details to administrators of a new scope.
        record_team_event(
            team, actor, TeamAuditLog.Event.DELETED, {"previous": before}, state=before
        )
        record_team_event(
            team, actor, TeamAuditLog.Event.CREATED, {"current": after}, state=after
        )
    elif before is None:
        record_team_event(
            team, actor, TeamAuditLog.Event.CREATED, {"current": after}, state=after
        )
    elif after is None:
        record_team_event(
            team, actor, TeamAuditLog.Event.DELETED, {"previous": before}, state=before
        )
    else:
        changes = {
            key: {"previous": before[key], "current": after[key]}
            for key in before
            if before[key] != after[key]
        }
        record_team_event(
            team, actor, TeamAuditLog.Event.CHANGED, changes, state=before
        )
    old_admins = {value["id"] for value in before["admins"]} if before else set()
    new_admins = {value["id"] for value in after["admins"]} if after else set()
    for user_id in new_admins - old_admins:
        record_admin_change(team, user_id, actor, granted=True, request=request)
    for user_id in old_admins - new_admins:
        record_admin_change(team, user_id, actor, granted=False, request=request)


def lock_team_for_audit(team: Group) -> None:
    """Follow Group.save's project-before-team lock order."""
    using = router.db_for_write(Group, instance=team)
    project_ids = (
        {
            value
            for value in Group.objects.using(using)
            .filter(pk=team.pk)
            .values_list("defining_project_id", flat=True)
            if value is not None
        }
        if team.pk
        else set()
    )
    if team.defining_project_id is not None:
        project_ids.add(team.defining_project_id)
    if project_ids:
        list(
            Project.objects.using(using)
            .filter(pk__in=project_ids)
            .order_by("pk")
            .select_for_update(no_key=True)
            .values_list("pk", flat=True)
        )
    if team.pk is not None:
        Group.objects.using(using).select_for_update(no_key=True).filter(
            pk=team.pk
        ).exists()


@contextmanager
def audit_team_changes(
    team: Group, actor: User, request: HttpRequest | Request | None = None
) -> Generator[None, None, None]:
    """Commit the mutation and its audit records together; ignore no-op writes."""
    using = router.db_for_write(Group, instance=team)
    if team.pk in _audited_teams.get():
        yield
        return
    with transaction.atomic(using=using):
        lock_team_for_audit(team)
        before = team_state(team)
        token = _audited_teams.set(
            _audited_teams.get() | {team.pk} if team.pk else _audited_teams.get()
        )
        try:
            yield
            log_team_changes(team, before, actor, request)
        finally:
            _audited_teams.reset(token)


def audit_admin_removal(
    team: Group, user_id: int, *, account_deleted: bool = False
) -> None:
    """Preserve revocations caused by membership deletion outside a team edit."""
    actor = get_acting_user()
    if actor is None or team.pk in _audited_teams.get():
        return
    if not account_deleted:
        record_admin_change(team, user_id, actor, granted=False)
    record_team_event(
        team, actor, TeamAuditLog.Event.CHANGED, {"admins": {"removed": [user_id]}}
    )
