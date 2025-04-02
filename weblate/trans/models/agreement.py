# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Component


class ContributorAgreementManager(models.Manager):
    def has_agreed(self, user: User, component: Component):
        if user.is_anonymous:
            return False
        cache_key = (user.pk, component.pk)
        if cache_key not in user.cla_cache:
            user.cla_cache[cache_key] = self.filter(
                component=component, user=user
            ).exists()
        return user.cla_cache[cache_key]

    def create(self, user: User, component: Component, **kwargs):
        user.cla_cache[user.pk, component.pk] = True
        return super().create(user=user, component=component, **kwargs)

    def order(self):
        return self.order_by("component__project__name", "component__name")


class ContributorAgreement(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.deletion.CASCADE, db_index=False
    )
    component = models.ForeignKey("trans.Component", on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)

    objects = ContributorAgreementManager()

    class Meta:
        unique_together = [("user", "component")]
        verbose_name = "contributor license agreement"
        verbose_name_plural = "contributor license agreements"

    def __str__(self) -> str:
        return f"{self.user.username}:{self.component}"
