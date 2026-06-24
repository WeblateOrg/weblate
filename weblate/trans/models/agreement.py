# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from weblate.auth.models import ClaCacheKey, ClaScope, User
    from weblate.trans.models import Category, Component, Project
    from weblate.workspaces.models import Workspace

    AgreementOwnerLookup = tuple[
        tuple[ClaScope, Category | Component | Project | Workspace]
    ]


class ContributorAgreementManager(models.Manager):
    def has_agreed(self, user: User, component: Component):
        if user.is_anonymous:
            return False
        owner_lookup = self.get_owner_lookup(component)
        cache_key = self.get_cache_key(user, owner_lookup)
        if cache_key not in user.cla_cache:
            user.cla_cache[cache_key] = self.filter(
                **dict(owner_lookup), user=user
            ).exists()
        return user.cla_cache[cache_key]

    def create(self, user: User, component: Component | None = None, **kwargs):
        if component is None:
            return super().create(user=user, **kwargs)
        owner_lookup = self.get_owner_lookup(component)
        user.cla_cache[self.get_cache_key(user, owner_lookup)] = True
        return super().create(user=user, **dict(owner_lookup), **kwargs)

    def get_owner_lookup(self, component: Component) -> AgreementOwnerLookup:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models.category import (
            Category,
        )

        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models.project import (
            Project,
        )

        # ruff: ignore[import-outside-top-level]
        from weblate.workspaces.models import (
            Workspace,
        )

        owner = component.get_effective_setting_owner("agreement")
        if isinstance(owner, Workspace):
            return (("workspace", owner),)
        if isinstance(owner, Project):
            return (("project", owner),)
        if isinstance(owner, Category):
            return (("category", owner),)
        return (("component", component),)

    def get_cache_key(
        self, user: User, owner_lookup: AgreementOwnerLookup
    ) -> ClaCacheKey:
        field, owner = owner_lookup[0]
        return (user.pk, field, owner.pk)

    def order(self):
        return self.order_by(
            "workspace__name",
            "project__name",
            "category__project__name",
            "category__name",
            "component__project__name",
            "component__name",
        )


class ContributorAgreement(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.deletion.CASCADE, db_index=False
    )
    component = models.ForeignKey(
        "trans.Component",
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    project = models.ForeignKey(
        "trans.Project",
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    category = models.ForeignKey(
        "trans.Category",
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    timestamp = models.DateTimeField(auto_now=True)

    objects = ContributorAgreementManager()

    class Meta:
        verbose_name = "contributor license agreement"
        verbose_name_plural = "contributor license agreements"
        constraints = [  # ruff: ignore[mutable-class-default]
            models.CheckConstraint(
                condition=(
                    models.Q(component__isnull=False)
                    & models.Q(project__isnull=True)
                    & models.Q(category__isnull=True)
                    & models.Q(workspace__isnull=True)
                )
                | (
                    models.Q(component__isnull=True)
                    & models.Q(project__isnull=False)
                    & models.Q(category__isnull=True)
                    & models.Q(workspace__isnull=True)
                )
                | (
                    models.Q(component__isnull=True)
                    & models.Q(project__isnull=True)
                    & models.Q(category__isnull=False)
                    & models.Q(workspace__isnull=True)
                )
                | (
                    models.Q(component__isnull=True)
                    & models.Q(project__isnull=True)
                    & models.Q(category__isnull=True)
                    & models.Q(workspace__isnull=False)
                ),
                name="contributor_agreement_single_scope",
            ),
            models.UniqueConstraint(
                fields=("user", "component"),
                condition=models.Q(component__isnull=False),
                name="contributor_agreement_unique_component",
            ),
            models.UniqueConstraint(
                fields=("user", "project"),
                condition=models.Q(project__isnull=False),
                name="contributor_agreement_unique_project",
            ),
            models.UniqueConstraint(
                fields=("user", "category"),
                condition=models.Q(category__isnull=False),
                name="contributor_agreement_unique_category",
            ),
            models.UniqueConstraint(
                fields=("user", "workspace"),
                condition=models.Q(workspace__isnull=False),
                name="contributor_agreement_unique_workspace",
            ),
        ]

    def __str__(self) -> str:
        owner = self.component or self.project or self.category or self.workspace
        return f"{self.user.username}:{owner}"
