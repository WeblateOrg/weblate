# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Self
from uuid import uuid4

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy

WORKSPACE_NAME_LENGTH = 100


class WorkspaceQuerySet(models.QuerySet["Workspace", "Workspace"]):
    def order(self) -> Self:
        return self.order_by("name")


class Workspace(models.Model):
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

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        update_fields = kwargs.get("update_fields")
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
        self.workspace_original_name = self.name
        self.workspace_original_name_managed = self.name_managed

    def get_absolute_url(self) -> str:
        return reverse("workspace", kwargs={"pk": self.pk})
