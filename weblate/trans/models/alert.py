# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
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

SEVERITY_BADGE_CLASSES: dict[int, str] = {
    AlertSeverity.INFO: "text-bg-info",
    AlertSeverity.WARNING: "text-bg-warning",
    AlertSeverity.ERROR: "text-bg-danger",
}

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
    dismissed_at = models.DateTimeField(null=True, blank=True)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dismissed_alerts",
    )
    dismissal_reason = models.CharField(max_length=500, blank=True)
    dismissal_fingerprint = models.CharField(max_length=64, blank=True)
    severity = models.PositiveSmallIntegerField(
        choices=AlertSeverity, default=AlertSeverity.ERROR, db_index=True
    )
    details = models.JSONField(default=dict)

    objects = AlertQuerySet.as_manager()

    class Meta:
        required_db_vendor = "postgresql"
        # ruff: ignore[mutable-class-default]
        unique_together = [("component", "name")]
        # ruff: ignore[mutable-class-default]
        indexes = [
            models.Index(
                fields=("component", "severity"),
                condition=Q(dismissed_at__isnull=True),
                name="trans_alert_active_idx",
            )
        ]
        verbose_name = "component alert"
        verbose_name_plural = "component alerts"

    def __str__(self) -> str:
        return str(self.obj.verbose)

    def save(self, *args, **kwargs) -> None:
        is_new = not self.id
        super().save(*args, **kwargs)
        if is_new and self.is_actionable:
            alert_class = get_alert_class(self.name)
            self.component.change_set.create(
                action=ActionEvents.ALERT,
                alert=self,
                details={
                    "alert": self.name,
                    "fingerprint": alert_class.get_dismissal_fingerprint(
                        self.component, self.details
                    ),
                },
            )

    @cached_property
    def obj(self) -> BaseAlert:
        return get_alert_class(self.name)(self, **self.details)

    def render(self, user: User) -> str:
        return self.obj.render(user)

    def get_documentation_url(self, user: User | None = None) -> str:
        return self.obj.get_documentation_url(self.component, user)

    @transaction.atomic
    def dismiss(self, user: User, reason: str = "") -> bool:
        if self.dismissed_at is not None or not self.obj.dismissible:
            return False
        dismissed_at = timezone.now()
        reason = reason.strip()[:500]
        self.dismissed_at = dismissed_at
        self.dismissed_by = user
        self.dismissal_reason = reason
        self.dismissal_fingerprint = self.obj.get_dismissal_fingerprint(
            self.component, self.details
        )
        self.save(
            update_fields=(
                "dismissed_at",
                "dismissed_by",
                "dismissal_reason",
                "dismissal_fingerprint",
            )
        )
        self.component.update_alert_caches()
        self.component.clear_prefetched_alerts()
        change_details = {
            "alert": self.name,
            "alert_snapshot": {
                "timestamp": self.timestamp.isoformat(),
                "updated": self.updated.isoformat(),
                "severity": self.severity,
                "details": self.details,
                "category": self.category,
            },
        }
        if reason:
            change_details["reason"] = reason
        self.component.change_set.create(
            action=ActionEvents.ALERT_DISMISSED,
            alert=self,
            user=user,
            details=change_details,
        )
        return True

    @property
    def is_dismissed(self) -> bool:
        return self.dismissed_at is not None

    def can_user_dismiss(self, user: User) -> bool:
        return self.obj.dismissible and self.obj.can_user_act(user, self.component)

    @property
    def category(self) -> str:
        return self.obj.category

    @property
    def is_problem(self) -> bool:
        return self.severity >= AlertSeverity.ERROR

    @property
    def is_actionable(self) -> bool:
        return self.severity >= AlertSeverity.WARNING

    @property
    def severity_class(self) -> str:
        return SEVERITY_BADGE_CLASSES.get(self.severity, "text-bg-secondary")
