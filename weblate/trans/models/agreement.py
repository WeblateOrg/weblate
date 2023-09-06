# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.db import models


class ContributorAgreementManager(models.Manager):
    def has_agreed(self, user, component):
        cache_key = (user.pk, component.pk)
        if cache_key not in user.cla_cache:
            user.cla_cache[cache_key] = self.filter(
                component=component, user=user
            ).exists()
        return user.cla_cache[cache_key]

    def create(self, user, component, **kwargs):
        user.cla_cache[(user.pk, component.pk)] = True
        return super().create(user=user, component=component, **kwargs)

    def order(self):
        return self.order_by("component__project__name", "component__name")


class ContributorAgreement(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.deletion.CASCADE, db_index=False
    )
    component = models.ForeignKey("Component", on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)

    objects = ContributorAgreementManager()

    class Meta:
        unique_together = [("user", "component")]
        verbose_name = "contributor agreement"
        verbose_name_plural = "contributor agreements"

    def __str__(self):
        return f"{self.user.username}:{self.component}"
