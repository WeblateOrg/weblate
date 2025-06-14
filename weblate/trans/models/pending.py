# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

from weblate.utils.db import using_postgresql
from weblate.utils.state import StringState

if TYPE_CHECKING:
    from datetime import datetime

    from weblate.auth.models import User
    from weblate.trans.models import Component, Project, Translation, Unit


class PendingChangeQuerySet(models.QuerySet):
    def for_project(self, project: Project):
        """Return pending changes for a specific component."""
        return self.filter(unit__translation__component__project=project)

    def for_component(self, component: Component):
        """Return pending changes for a specific component."""
        return self.filter(unit__translation__component=component)

    def for_translation(self, translation: Translation):
        """Return pending changes for a specific translation."""
        return self.filter(unit__translation=translation)

    def older_than(self, timestamp: datetime):
        """Return pending changes older than given timestamp."""
        return self.filter(timestamp__lt=timestamp)

    def select_for_update(self) -> PendingChangeQuerySet:  # type: ignore[override]
        if using_postgresql():
            # Use weaker locking and limit locking to this table only
            return super().select_for_update(no_key=True, of=("self",))
        # Discard any select_related to avoid locking additional tables
        return super().select_for_update().select_related(None)


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
    add_unit = models.BooleanField(default=False)

    objects = PendingChangeQuerySet.as_manager()

    class Meta:
        app_label = "trans"
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
        *,
        author: User | None = None,
        target: str | None = None,
        explanation: str | None = None,
        state: int | None = None,
        add_unit: bool = False,
    ) -> PendingUnitChange:
        """Store complete change data for a unit by a specific author."""
        if target is None:
            target = unit.target
        if explanation is None:
            explanation = unit.explanation
        if state is None:
            state = unit.state
        if author is None:
            author = unit.get_last_content_change()[0]

        pending, _ = cls.objects.update_or_create(
            unit=unit,
            author=author,
            defaults={
                "target": target,
                "explanation": explanation,
                "state": state,
                "add_unit": add_unit,
            },
        )
        return pending
