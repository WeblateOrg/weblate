# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.utils.functional import cached_property

from weblate.trans.actions import ActionEvents
from weblate.trans.alerts.base import AlertSeverity, BaseAlert, ErrorAlert, MultiAlert
from weblate.trans.alerts.registry import (
    ALERTS,
    ALERTS_IMPORT,
    get_alert_class,
    register,
    update_alerts,
)

if TYPE_CHECKING:
    from weblate.auth.models import User

__all__ = [
    "ALERTS",
    "ALERTS_IMPORT",
    "Alert",
    "AlertQuerySet",
    "AlertSeverity",
    "BaseAlert",
    "ErrorAlert",
    "MultiAlert",
    "register",
    "update_alerts",
]


class AlertQuerySet(models.QuerySet["Alert", "Alert"]):
    def order(self) -> AlertQuerySet:
        return self.order_by(
            "-severity", "name", "component__project__name", "component__name", "pk"
        )

    def order_component(self) -> AlertQuerySet:
        return self.order_by("-severity", "name", "pk")


class Alert(models.Model):
    component = models.ForeignKey(
        "trans.Component", on_delete=models.deletion.CASCADE, db_index=False
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=150)
    dismissed = models.BooleanField(default=False, db_index=True)
    severity = models.PositiveSmallIntegerField(
        choices=AlertSeverity, default=AlertSeverity.ERROR, db_index=True
    )
    details = models.JSONField(default=dict)

    objects = AlertQuerySet.as_manager()

    class Meta:
        unique_together = [("component", "name")]  # noqa: RUF012
        verbose_name = "component alert"
        verbose_name_plural = "component alerts"

    def __str__(self) -> str:
        return str(self.obj.verbose)

    def save(self, *args, **kwargs) -> None:
        is_new = not self.id
        super().save(*args, **kwargs)
        if is_new and self.is_problem:
            self.component.change_set.create(
                action=ActionEvents.ALERT,
                alert=self,
                details={"alert": self.name},
            )

    @cached_property
    def obj(self) -> BaseAlert:
        return get_alert_class(self.name)(self, **self.details)

    def render(self, user: User) -> str:
        return self.obj.render(user)

    @property
    def is_problem(self) -> bool:
        return self.severity >= AlertSeverity.ERROR
