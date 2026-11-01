# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Role assignments for visibility regression matrices."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from django.test.utils import TestContextDecorator

from weblate.auth.models import Group, Permission, Role, User
from weblate.trans.tests.utils import clear_users_cache

if TYPE_CHECKING:
    from django.db.models import Model


class VisibilityPermissions(TestContextDecorator):
    """Configure actual roles while refreshing cached test-user permissions."""

    def __init__(
        self, *, directory: str | None = None, profile: str | None = None
    ) -> None:
        super().__init__()
        self.directory = directory
        self.profile = profile

    def enable(self) -> None:
        self.saved = []
        permissions = set()
        if self.directory is not None:
            permissions.update({"user.browse", "user.search"})
        if self.profile is not None:
            permissions.add("user.profile")
        for role in Role.objects.filter(
            permissions__codename__in=permissions
        ).distinct():
            current = list(role.permissions.all())
            self.saved.append((role, current))
            role.permissions.remove(*[p for p in current if p.codename in permissions])
        self.roles = []
        for team, codenames in (
            (
                "Users",
                (
                    (
                        {"user.browse", "user.search"}
                        if self.directory == "all"
                        else {"user.search"}
                        if self.directory == "scoped"
                        else set()
                    )
                    | (
                        {"user.profile"}
                        if self.profile in {"public", "authenticated"}
                        else set()
                    )
                ),
            ),
            ("Guests", {"user.profile"} if self.profile == "public" else set()),
        ):
            if codenames:
                role = Role.objects.create(name=f"Visibility test {team}")
                role.permissions.set(Permission.objects.filter(codename__in=codenames))
                Group.objects.get(name=team, internal=True).roles.add(role)
                self.roles.append(role)
        original = User.has_perm

        def has_perm(user: User, perm: str, obj: Model | None = None) -> bool:
            user.clear_permissions_cache()
            return bool(original(user, perm, obj))

        self.patcher = patch.object(User, "has_perm", has_perm)
        self.patcher.start()
        clear_users_cache()

    def disable(self) -> None:
        self.patcher.stop()
        for role in self.roles:
            role.delete()
        for role, permissions in self.saved:
            role.permissions.set(permissions)
        clear_users_cache()
