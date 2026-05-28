# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, ClassVar, Self
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy

from weblate.trans.actions import ActionEvents

if TYPE_CHECKING:
    from collections.abc import Collection

    from django.db.models import QuerySet

    from weblate.auth.models import Group, User

WORKSPACE_NAME_LENGTH = 100

WORKSPACE_ADMINISTRATION_ROLE = "Workspace administration"
WORKSPACE_ADD_PROJECT_ROLE = "Add workspace projects"
WORKSPACE_OWNERS_GROUP = "Owners"
WORKSPACE_PROJECT_CREATORS_GROUP = "Project creators"
WORKSPACE_GROUPS = {
    WORKSPACE_OWNERS_GROUP: (WORKSPACE_ADMINISTRATION_ROLE,),
    WORKSPACE_PROJECT_CREATORS_GROUP: (WORKSPACE_ADD_PROJECT_ROLE,),
}


class WorkspaceQuerySet(models.QuerySet["Workspace", "Workspace"]):
    def order(self) -> Self:
        return self.order_by("name")


class Workspace(models.Model):
    AUDIT_SETTINGS: ClassVar[tuple[str, ...]] = ("name",)

    # Name loaded with this instance; used to detect manual name edits.
    workspace_original_name: str
    # Name management flag loaded with this instance.
    workspace_original_name_managed: bool

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(
        verbose_name=gettext_lazy("Workspace name"),
        max_length=WORKSPACE_NAME_LENGTH,
        help_text=gettext_lazy("Display name"),
    )
    name_managed = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=gettext_lazy("Managed name"),
        help_text=gettext_lazy("Whether Weblate can update the name automatically."),
    )

    objects = WorkspaceQuerySet.as_manager()

    class Meta:
        verbose_name = "Workspace"
        verbose_name_plural = "Workspaces"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.workspace_original_name = self.name
        self.workspace_original_name_managed = self.name_managed
        self.acting_user: User | None = None

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        create_groups = self._state.adding
        update_fields = kwargs.get("update_fields")
        if not self._state.adding:
            old = Workspace.objects.get(pk=self.pk)
            self.generate_changes(old, update_fields=update_fields)

        name_saved = update_fields is None or "name" in update_fields
        managed_saved = update_fields is None or "name_managed" in update_fields
        name_changed = self.name != self.workspace_original_name
        managed_changed = self.name_managed != self.workspace_original_name_managed
        if (
            self.pk is not None
            and self.name_managed
            and name_saved
            and name_changed
            and not (managed_saved and managed_changed)
        ):
            self.name_managed = False
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "name_managed"}

        super().save(*args, **kwargs)
        if create_groups:
            self.setup_groups()
        self.workspace_original_name = self.name
        self.workspace_original_name_managed = self.name_managed

    def get_absolute_url(self) -> str:
        return reverse("workspace", kwargs={"pk": self.pk})

    def get_url_path(self) -> tuple[str, ...]:
        return ("-", "workspace", str(self.pk))

    def can_view(self, user: User) -> bool:
        if user.allowed_projects.filter(workspace=self).exists():
            return True
        if any(
            user.has_perm(permission, self)
            for permission in (
                "workspace.edit",
                "workspace.add_project",
                "workspace.edit_members",
            )
        ):
            return True
        if user.has_perm("management.use"):
            return True
        if "weblate.billing" in settings.INSTALLED_APPS:
            with suppress(AttributeError, ObjectDoesNotExist):
                return bool(user.has_perm("meta:billing.view", self.billing))
        return False

    def setup_groups(self) -> dict[str, Group]:
        from weblate.auth.data import SELECTION_MANUAL  # noqa: PLC0415
        from weblate.auth.models import Group, Role  # noqa: PLC0415

        result = {}
        for group_name, roles in WORKSPACE_GROUPS.items():
            group, created = Group.objects.get_or_create(
                defining_workspace=self,
                name=group_name,
                defaults={
                    "internal": True,
                    "project_selection": SELECTION_MANUAL,
                    "language_selection": SELECTION_MANUAL,
                },
            )
            if created or not group.roles.exists():
                group.roles.set(Role.objects.filter(name__in=roles))
            result[group_name] = group
        return result

    def get_owners_group(self) -> Group:
        return self.setup_groups()[WORKSPACE_OWNERS_GROUP]

    def add_owner(self, user: User, request=None) -> None:
        user.add_team(request, self.get_owners_group())

    def users_with_permission(self, permission: str) -> QuerySet[User, User]:
        from weblate.auth.models import User  # noqa: PLC0415

        return (
            User.objects.filter(
                is_active=True,
                is_bot=False,
                team_memberships__limit_languages__isnull=True,
                team_memberships__group__defining_workspace=self,
                team_memberships__group__roles__permissions__codename=permission,
            )
            .distinct()
            .order()
        )

    def generate_changes(
        self, old: Workspace, update_fields: Collection[str] | None = None
    ) -> None:
        from weblate.trans.models.audit import log_setting_changes  # noqa: PLC0415

        log_setting_changes(
            self,
            old,
            self.AUDIT_SETTINGS,
            ActionEvents.WORKSPACE_SETTING_CHANGE,
            self.acting_user,
            update_fields,
        )
