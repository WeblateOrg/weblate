# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models
from django.db.models import (
    BooleanField,
    Case,
    F,
    OuterRef,
    Q,
    Subquery,
    TextField,
    When,
)
from django.db.models.fields.json import KT
from django.db.models.functions import Cast
from django.utils import timezone

from weblate.utils.db import using_postgresql
from weblate.utils.state import STATE_APPROVED, STATE_FUZZY, StringState
from weblate.utils.version import GIT_VERSION

if TYPE_CHECKING:
    from datetime import datetime

    from weblate.auth.models import User
    from weblate.trans.models import Component, Translation, Unit


class PendingChangeQuerySet(models.QuerySet):
    def for_component(
        self, component: Component, *, apply_filters: bool, include_linked: bool = False
    ):
        """Return pending changes for a specific component."""
        component_filter = Q(unit__translation__component=component)
        if include_linked:
            component_filter |= Q(
                unit__translation__component__linked_component=component
            )

        base_qs = self.filter(component_filter)
        if not apply_filters:
            return base_qs

        commit_policy = component.project.commit_policy
        return self._apply_retry_and_policy_filters(
            base_qs, revision=None, commit_policy=commit_policy
        )

    def for_translation(self, translation: Translation, apply_filters: bool = True):
        """Return pending changes for a specific translation."""
        base_qs = self.filter(unit__translation=translation)
        if not apply_filters:
            return base_qs

        commit_policy = translation.component.project.commit_policy
        return self._apply_retry_and_policy_filters(
            base_qs, revision=translation.revision, commit_policy=commit_policy
        )

    def _apply_retry_and_policy_filters(
        self, base_queryset: models.QuerySet, revision: str | None, commit_policy: int
    ) -> models.QuerySet:
        """
        Apply retry eligibility and commit policy filters.

        Args:
            base_queryset: Pre-filtered queryset (by component or translation)
            revision: Specific revision string, or None to use join-based comparison
            commit_policy: The commit policy to apply

        Returns:
            Filtered queryset with all filters applied

        """
        from weblate.trans.models.project import CommitPolicyChoices

        one_week_ago = timezone.now() - timedelta(days=7)

        annotations_: dict[str, Any] = {
            # use KT and explicitly cast key value to string to avoid
            # django from treating string comparison values for RHS as JSON
            # on mariadb and mysql.
            "failed_revision": Cast(KT("metadata__failed_revision"), TextField()),
            "weblate_version": Cast(KT("metadata__weblate_version"), TextField()),
            "last_failed": Cast(KT("metadata__last_failed"), TextField()),
        }

        # Component-level queries require joining unit.translation for revision;
        # translation-level queries use the provided revision directly
        if revision is None:
            annotations_["translation_revision"] = Cast(
                "unit__translation__revision", TextField()
            )
            revision_comparison = ~Q(failed_revision=F("translation_revision"))
        else:
            revision_comparison = ~Q(failed_revision=revision)

        # filter changes that are new or eligible for retry
        eligible_for_attempt_filter = (
            Q(metadata__last_failed__isnull=True)
            | revision_comparison
            | ~Q(weblate_version=GIT_VERSION)
            | Q(last_failed__lt=one_week_ago.isoformat())
        )

        annotations_["eligible_for_attempt"] = Case(
            When(eligible_for_attempt_filter, then=True),
            default=False,
            output_field=BooleanField(),
        )

        qs = (
            base_queryset.annotate(**annotations_)
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

        if commit_policy == CommitPolicyChoices.ALL:
            return qs

        filters = []
        if commit_policy == CommitPolicyChoices.WITHOUT_NEEDS_EDITING:
            filters.append(~Q(state=STATE_FUZZY))
        elif commit_policy == CommitPolicyChoices.APPROVED_ONLY:
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
        # update current fields in disk_state details for comparison of
        # uncommitted disk state with incoming changes during check_sync.
        unit.store_disk_state()

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
