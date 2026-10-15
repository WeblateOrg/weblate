# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Database filters for role permission scopes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from weblate.auth.data import (
    SELECTION_ALL,
    SELECTION_ALL_PROTECTED,
    SELECTION_ALL_PUBLIC,
)

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.auth.permissions import PermissionLanguageScope


def _related_lookup(path: str, field: str) -> str:
    return f"{path}__{field}" if path else field


# ruff: ignore[complex-structure]
def get_permission_scope_query(
    user: User,
    permission: str,
    *,
    component_path: str,
    language_path: str | None = None,
) -> Q:
    """
    Build a role-scope filter for objects related to components.

    This covers project and component role assignment, component restrictions,
    language limits, project access selection, user blocks, and enforced 2FA.
    Feature-specific rules such as locks, workflows, or repository ownership
    have to be applied by the caller.
    """
    if user.is_superuser:
        return Q()

    # Importing this at module load time would introduce a model import cycle.
    from weblate.trans.models.project import Project  # ruff: ignore[import-outside-top-level]

    component_lookup = _related_lookup(component_path, "pk")
    project_lookup = _related_lookup(component_path, "project_id")
    restricted_lookup = _related_lookup(component_path, "restricted")
    access_control_lookup = _related_lookup(component_path, "project__access_control")
    enforced_2fa_lookup = _related_lookup(component_path, "project__enforced_2fa")

    unrestricted = Q(**{restricted_lookup: False})
    project_scopes = {
        -SELECTION_ALL: unrestricted,
        -SELECTION_ALL_PUBLIC: unrestricted
        & Q(**{access_control_lookup: Project.ACCESS_PUBLIC}),
        -SELECTION_ALL_PROTECTED: unrestricted
        & Q(**{access_control_lookup: Project.ACCESS_PROTECTED}),
    }
    result = Q(pk__in=())

    def apply_languages(
        scope: Q, languages: PermissionLanguageScope | None
    ) -> Q | None:
        if languages is None:
            return scope
        if language_path is not None:
            return scope & Q(**{f"{language_path}__in": languages.language_ids})
        # Team language selections historically limit translation actions only.
        # Per-membership limits also restrict component-wide checks.
        if languages.membership_limited:
            return None
        return scope

    for project_id, project_permissions in user.project_permissions.items():
        project_scope = project_scopes.get(project_id)
        if project_scope is None:
            if project_id < 0:
                continue
            project_scope = unrestricted & Q(**{project_lookup: project_id})
        for permissions, languages in project_permissions:
            if permissions is None or permission not in permissions:
                continue
            scope = apply_languages(project_scope, languages)
            if scope is not None:
                result |= scope

    for component_id, component_permissions in user.component_permissions.items():
        component_scope = Q(**{component_lookup: component_id})
        for permissions, languages in component_permissions:
            if permission not in permissions:
                continue
            scope = apply_languages(component_scope, languages)
            if scope is not None:
                result |= scope

    blocked_project_ids = {
        project_id
        for project_id, scoped_permissions in user.project_permissions.items()
        if project_id > 0 and scoped_permissions == [(None, None)]
    }
    if blocked_project_ids:
        result &= ~Q(**{f"{project_lookup}__in": blocked_project_ids})

    if not user.is_bot and not user.profile.has_2fa:
        result &= Q(**{enforced_2fa_lookup: False})

    return result
