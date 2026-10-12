# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy

if TYPE_CHECKING:
    from typing import Self


class SavedSearchQuerySet(models.QuerySet["SavedSearch", "SavedSearch"]):
    def order(self) -> Self:
        return self.order_by("name")


class SavedSearch(models.Model):
    """Search query saved for a project or for a single user."""

    project = models.ForeignKey(
        "trans.Project",
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
        db_index=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
        db_index=False,
    )
    name = models.CharField(
        verbose_name=gettext_lazy("Saved search name"), max_length=190
    )
    query = models.TextField(verbose_name=gettext_lazy("Search query"))
    description = models.CharField(
        verbose_name=gettext_lazy("Search description"),
        max_length=250,
        blank=True,
        default="",
    )

    objects = SavedSearchQuerySet.as_manager()

    class Meta:
        required_db_vendor = "postgresql"
        app_label = "trans"
        verbose_name = "saved search"
        verbose_name_plural = "saved searches"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    Q(project__isnull=False, user__isnull=True)
                    | Q(project__isnull=True, user__isnull=False)
                ),
                name="trans_saved_search_single_scope",
            ),
            models.UniqueConstraint(
                fields=["project", "name"],
                condition=Q(user__isnull=True),
                name="trans_saved_search_project_name",
                violation_error_message=gettext_lazy(
                    "A saved search with this name already exists."
                ),
            ),
            models.UniqueConstraint(
                fields=["user", "name"],
                condition=Q(project__isnull=True),
                name="trans_saved_search_user_name",
                violation_error_message=gettext_lazy(
                    "A saved search with this name already exists."
                ),
            ),
        ]

    def __str__(self) -> str:
        return self.name
