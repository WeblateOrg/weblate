# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.postgres import indexes as postgres_indexes
from django.db import models
from django.utils import timezone
from weblate_language_data.utils import gettext_noop

from weblate.trans.actions import ActionEvents
from weblate.trans.mixins import UserDisplayMixin
from weblate.utils.antispam import report_spam
from weblate.utils.request import get_ip_address, get_user_agent_raw
from weblate.utils.state import STATE_NEEDS_CHECKING, STATE_NEEDS_REWRITING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.trans.models.unit import Unit


def schedule_comment_stats_update(translation_ids: Iterable[int]) -> None:
    """Queue one stats update for translations affected by a comment deletion."""
    # ruff: ignore[import-outside-top-level]
    from weblate.utils.tasks import update_translation_stats

    pks = list(translation_ids)
    if pks:
        update_translation_stats.delay_on_commit(pks)


class CommentManager(models.Manager):
    def add(
        self,
        request: AuthenticatedHttpRequest,
        unit: Unit,
        text: str,
        scope: str,
        *,
        user: User | None = None,
        timestamp: datetime | None = None,
    ) -> Comment:
        """Add comment to this unit."""
        # Is this source or target comment?
        unit_scope = unit.source_unit if scope in {"global", "report"} else unit

        if user is None:
            user = request.user
        kwargs = {
            "user": user,
            "unit": unit_scope,
            "comment": text,
            "userdetails": {
                "address": get_ip_address(request),
                "agent": get_user_agent_raw(request),
            },
        }
        if timestamp is not None:
            kwargs["timestamp"] = timestamp

        new_comment = self.create(**kwargs)
        user.profile.increase_count("commented")
        unit_scope.change_set.create(
            comment=new_comment,
            action=ActionEvents.COMMENT,
            user=user,
            author=user,
            details={"comment": text},
        )

        component = unit_scope.translation.component
        user.profile.watch_on_contribution(component.project)

        # Add review label/flag
        if scope == "report":
            if component.has_template():
                if unit_scope.translated and not unit_scope.readonly:
                    unit_scope.translate(
                        user,
                        unit_scope.target,
                        STATE_NEEDS_CHECKING
                        if unit_scope.is_source
                        else STATE_NEEDS_REWRITING,
                        change_action=ActionEvents.MARKED_EDIT,
                    )
            else:
                label = component.project.label_set.get_or_create(
                    name=gettext_noop("Source needs review"), defaults={"color": "red"}
                )[0]
                if not unit_scope.labels.filter(pk=label.pk).exists():
                    unit_scope.labels.add(label)
                    unit_scope.change_set.create(
                        action=ActionEvents.LABEL_ADD,
                        user=user,
                        author=user,
                        details={"label": label.name},
                    )

        return new_comment


class CommentQuerySet(models.QuerySet["Comment", "Comment"]):
    def prefetch(self):
        return self.select_related("user")

    def order(self):
        return self.order_by("timestamp")

    def delete(self):
        translation_ids = list(
            self.values_list("unit__translation_id", flat=True).distinct()
        )
        result = super().delete()
        schedule_comment_stats_update(translation_ids)
        return result


class Comment(models.Model, UserDisplayMixin):
    unit = models.ForeignKey("trans.Unit", on_delete=models.deletion.CASCADE)
    comment = models.TextField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    resolved = models.BooleanField(default=False, db_index=True)
    userdetails = models.JSONField(default=dict)

    objects = CommentManager.from_queryset(CommentQuerySet)()

    class Meta:
        app_label = "trans"
        verbose_name = "string comment"
        verbose_name_plural = "string comments"
        # ruff: ignore[mutable-class-default]
        indexes = [
            postgres_indexes.GinIndex(
                postgres_indexes.OpClass(models.F("comment"), name="gin_trgm_ops"),
                models.F("unit"),
                name="comment_comment_fulltext",
            ),
        ]

    def __str__(self) -> str:
        return f"comment for {self.unit} by {self.user.username if self.user else 'unknown'}"

    def report_spam(self) -> None:
        report_spam(
            self.userdetails["address"], self.userdetails["agent"], self.comment
        )

    def resolve(self, user: User) -> None:
        self.unit.change_set.create(
            comment=self,
            action=ActionEvents.COMMENT_RESOLVE,
            user=user,
            author=self.user,
            details={"comment": self.comment},
        )
        self.resolved = True
        self.save(update_fields=["resolved"])

    # pylint: disable-next=arguments-renamed
    def delete(self, user=None, using=None, keep_parents=False) -> None:
        translation_id = self.unit.translation_id
        self.unit.change_set.create(
            action=ActionEvents.COMMENT_DELETE,
            user=user,
            author=self.user,
            details={"comment": self.comment},
        )
        super().delete(using=using, keep_parents=keep_parents)
        schedule_comment_stats_update([translation_id])
