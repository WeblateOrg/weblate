# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy

from weblate.workspaces.models import Workspace

from .component import Component

if TYPE_CHECKING:
    from uuid import UUID

    from weblate.auth.models import User

    from .category import Category
    from .project import Project


class ReportQuerySet(models.QuerySet["Report", "Report"]):
    def metadata(self) -> Self:
        return self.defer("data", "parameters")

    def filter_access(self, user: User) -> Self:
        if not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self

        accessible_projects = user.allowed_projects.order_by()
        accessible_components = Component.objects.filter_access(user).order_by()

        if user.has_perm("management.use"):
            accessible_workspaces = Workspace.objects.all()
        else:
            workspace_ids: set[UUID] = set()
            for permission in (
                "workspace.edit",
                "workspace.add_project",
                "workspace.edit_members",
            ):
                workspace_ids.update(user.workspace_ids_with_perm(permission))
            workspace_access = Q(projects__in=accessible_projects) | Q(
                pk__in=workspace_ids
            )
            if "weblate.billing" in settings.INSTALLED_APPS and user.has_perm(
                "billing.manage"
            ):
                workspace_access |= Q(billing__isnull=False)
            accessible_workspaces = Workspace.objects.filter(
                workspace_access
            ).distinct()

        has_2fa = user.is_bot or user.profile.has_2fa
        report_projects = user.projects_with_perm("reports.view").order_by()
        if not has_2fa:
            report_projects = report_projects.filter(enforced_2fa=False)

        component_permission_ids = {
            component_id
            for component_id, scoped_permissions in user.component_permissions.items()
            if any(
                permissions is not None
                and "reports.view" in permissions
                and (languages is None or not languages.membership_limited)
                for permissions, languages in scoped_permissions
            )
        }
        report_components = Component.objects.filter(
            Q(restricted=False, project__in=report_projects)
            | Q(pk__in=component_permission_ids)
        )
        if not has_2fa:
            report_components = report_components.filter(project__enforced_2fa=False)

        scope_access = (
            Q(
                workspace__isnull=True,
                project__isnull=True,
                category__isnull=True,
                component__isnull=True,
            )
            | Q(workspace__in=accessible_workspaces)
            | Q(project__in=accessible_projects)
            | Q(category__project__in=accessible_projects)
            | Q(component__in=accessible_components)
        )
        permission_access = (
            Q(workspace_id__in=user.workspace_ids_with_perm("reports.view"))
            | Q(project__in=report_projects)
            | Q(category__project__in=report_projects)
            | Q(component__in=report_components)
        )
        creator_access = Q(creator=user, parameters__own_data=True)
        return self.filter(scope_access & (creator_access | permission_access))


class Report(models.Model):
    class Kind(models.TextChoices):
        CREDITS = "credits", gettext_lazy("Credits")
        CONTRIBUTOR_STATS = "contributor_stats", gettext_lazy("Contributor stats")
        COST_ESTIMATE = "cost_estimate", gettext_lazy("Cost estimate")
        TRANSLATOR_WORK = "translator_work", gettext_lazy("Translator work analysis")

    CURRENT_VERSION: ClassVar[int] = 1

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.deletion.CASCADE,
        related_name="generated_reports",
    )
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(max_length=32, choices=Kind, db_index=True)
    version = models.PositiveSmallIntegerField(default=CURRENT_VERSION)
    parameters = models.JSONField(default=dict)
    data = models.JSONField(default=dict)
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
        related_name="reports",
    )
    project = models.ForeignKey(
        "trans.Project",
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
        related_name="reports",
    )
    category = models.ForeignKey(
        "trans.Category",
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
        related_name="reports",
    )
    component = models.ForeignKey(
        "trans.Component",
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
        related_name="reports",
    )

    objects = ReportQuerySet.as_manager()

    class Meta:
        ordering = ("-created", "-pk")
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=(
                    Q(
                        workspace__isnull=True,
                        project__isnull=True,
                        category__isnull=True,
                        component__isnull=True,
                    )
                    | Q(
                        workspace__isnull=False,
                        project__isnull=True,
                        category__isnull=True,
                        component__isnull=True,
                    )
                    | Q(
                        workspace__isnull=True,
                        project__isnull=False,
                        category__isnull=True,
                        component__isnull=True,
                    )
                    | Q(
                        workspace__isnull=True,
                        project__isnull=True,
                        category__isnull=False,
                        component__isnull=True,
                    )
                    | Q(
                        workspace__isnull=True,
                        project__isnull=True,
                        category__isnull=True,
                        component__isnull=False,
                    )
                ),
                name="trans_report_single_scope",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} #{self.pk}"

    @property
    def scope(self) -> Workspace | Project | Category | Component | None:
        return self.workspace or self.project or self.category or self.component

    def can_access(self, user: User) -> bool:
        if not user.is_authenticated:
            return False
        if self.workspace is not None and not self.workspace.can_view(user):
            return False
        if (
            self.project_id
            and not user.allowed_projects.filter(pk=self.project_id).exists()
        ):
            return False
        if (
            self.category is not None
            and not user.allowed_projects.filter(pk=self.category.project_id).exists()
        ):
            return False
        if self.component is not None and not user.can_access_component(self.component):
            return False
        creator_access = (
            self.creator_id == user.pk and self.parameters.get("own_data") is True
        )
        return creator_access or bool(user.has_perm("reports.view", self.scope))


REPORT_KIND_CHOICES = Report.Kind.choices
