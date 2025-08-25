# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models import BooleanField, Case, OuterRef, Q, Subquery, When
from django.db.models.fields.json import KT
from django.utils import timezone

from weblate.utils.db import using_postgresql
from weblate.utils.state import STATE_APPROVED, STATE_FUZZY, StringState
from weblate.utils.version import GIT_VERSION

if TYPE_CHECKING:
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
        from weblate.trans.models.project import CommitPolicyChoices

        one_week_ago = timezone.now() - timedelta(days=7)

        # filter changes that are new or eligible for retry
        eligible_for_attempt_filter = (
            Q(metadata__last_failed__isnull=True)
            | ~Q(failed_revision=translation.revision)
            | ~Q(weblate_version=GIT_VERSION)
            | Q(metadata__last_failed__lt=one_week_ago.isoformat())
        )

        qs = (
            self.filter(unit__translation=translation)
            .annotate(
                # use KT to extract JSON values for string comparison
                # to prevent quoting issues with mariadb/mysql.
                failed_revision=KT("metadata__failed_revision"),
                weblate_version=KT("metadata__weblate_version"),
                eligible_for_attempt=Case(
                    When(eligible_for_attempt_filter, then=True),
                    default=False,
                    output_field=BooleanField(),
                ),
            )
            .filter(Q(eligible_for_attempt=True) | Q(metadata__blocking_unit=True))
            .order_by("unit_id", "timestamp")
            .values_list(
                "pk", "unit_id", "metadata__blocking_unit", "eligible_for_attempt"
            )
        )

        blocked_units = set()
        eligible_pks = []

        # failed changes that are not yet eligible for retry and have blocking_unit=True
        # should prevent all newer changes from being committed
        for pk, unit_id, blocking_unit, eligible_for_attempt in qs.iterator():
            if unit_id in blocked_units:
                continue

            if eligible_for_attempt:
                eligible_pks.append(pk)
            elif blocking_unit:
                blocked_units.add(unit_id)

        qs = self.filter(pk__in=eligible_pks)

        policy = translation.component.project.commit_policy
        if policy == CommitPolicyChoices.ALL:
            return qs

        filters = []
        if policy == CommitPolicyChoices.WITHOUT_NEEDS_EDITING:
            filters.append(~Q(state=STATE_FUZZY))
        elif policy == CommitPolicyChoices.APPROVED_ONLY:
            filters.append(Q(state=STATE_APPROVED))

        # For each unit, finds the last change that makes it eligible for committing
        # based on the project's commit policy, and returns all changes up to and
        # including that change.
        latest_eligible_changes = (
            PendingUnitChange.objects.filter(*filters, unit_id=OuterRef("unit_id"))
            .order_by("-timestamp")
            .values("timestamp")[:1]
        )
        return qs.filter(timestamp__lte=Subquery(latest_eligible_changes))

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
        "trans.Unit",
        on_delete=models.CASCADE,
        related_name="pending_changes",
        db_index=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=True,
    )
    target = models.TextField(default="", blank=True)
    explanation = models.TextField(default="", blank=True)
    source_unit_explanation = models.TextField(default="", blank=True)
    state = models.IntegerField(default=0, choices=StringState.choices, db_index=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    add_unit = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True, null=False)

    objects = PendingChangeQuerySet.as_manager()

    class Meta:
        app_label = "trans"
        verbose_name = "pending change"
        verbose_name_plural = "pending changes"

    def __str__(self) -> str:
        return f"Pending change for {self.unit} -> {self.target} by {self.author}"

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
        source_unit_explanation: str | None = None,
        timestamp: datetime | None = None,
    ) -> PendingUnitChange:
        """Store complete change data for a unit by a specific author."""
        if target is None:
            target = unit.target
        if explanation is None:
            explanation = unit.explanation
        if state is None:
            state = unit.state
        if source_unit_explanation is None:
            source_unit_explanation = unit.source_unit.explanation
        if author is None:
            author = unit.get_last_content_change()[0]

        kwargs = {
            "unit": unit,
            "author": author,
            "target": target,
            "explanation": explanation,
            "state": state,
            "add_unit": add_unit,
            "source_unit_explanation": source_unit_explanation,
        }
        if timestamp is not None:
            kwargs["timestamp"] = timestamp

        pending_unit_change = PendingUnitChange(**kwargs)
        pending_unit_change.save()
        return pending_unit_change
