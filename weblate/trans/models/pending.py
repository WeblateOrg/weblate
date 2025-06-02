# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

from weblate.utils.state import StringState

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Unit


class PendingChangeQuerySet(models.QuerySet):
    def for_project(self, project):
        """Return pending changes for a specific component."""
        return self.filter(unit__translation__component__project=project)

    def for_component(self, component):
        """Return pending changes for a specific component."""
        return self.filter(unit__translation__component=component)

    def for_translation(self, translation):
        """Return pending changes for a specific translation."""
        return self.filter(unit__translation=translation)

    def older_than(self, timestamp):
        """Return pending changes older than given timestamp."""
        return self.filter(timestamp__lt=timestamp)


class PendingUnitChange(models.Model):
    """Stores actual change data that needs to be committed to a repository."""

    unit = models.ForeignKey(
        "trans.Unit", on_delete=models.CASCADE, related_name="pending_changes"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )
    target = models.TextField(default="", blank=True)
    explanation = models.TextField(default="", blank=True)
    state = models.IntegerField(
        default=0,
        choices=StringState.choices,
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    details = models.JSONField(default=dict, blank=True)

    objects = PendingChangeQuerySet.as_manager()

    class Meta:
        app_label = "trans"
        indexes = [
            models.Index(fields=["timestamp"]),
        ]
        # Ensure each author can only have one pending change per unit at a time
        unique_together = [("unit", "author")]
        verbose_name = "pending change"
        verbose_name_plural = "pending changes"

    def __str__(self) -> str:
        return f"Pending change for {self.unit} by {self.author}"

    @classmethod
    def store_unit_change(
        cls,
        unit: Unit,
        author: User,
        *,
        target: str | None = None,
        explanation: str | None = None,
        state: int | None = None,
        details: dict | None = None,
    ) -> PendingUnitChange:
        """Store complete change data for a unit by a specific author."""
        from weblate.auth.models import get_anonymous

        if target is None:
            target = unit.target
        if explanation is None:
            explanation = unit.explanation
        if state is None:
            state = unit.state
        if details is None:
            details = unit.details

        pending, _ = cls.objects.update_or_create(
            unit=unit,
            author=author or get_anonymous(),
            defaults={
                "target": target,
                "explanation": explanation,
                "state": state,
                "details": details,
            },
        )
        return pending
