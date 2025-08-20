# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone
from weblate_language_data.utils import gettext_noop

from weblate.trans.actions import ActionEvents
from weblate.trans.mixins import UserDisplayMixin
from weblate.utils.antispam import report_spam
from weblate.utils.request import get_ip_address, get_user_agent_raw
from weblate.utils.state import STATE_FUZZY

if TYPE_CHECKING:
    from datetime import datetime

    from weblate.auth.models import AuthenticatedHttpRequest, Unit, User


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

        # Add review label/flag
        if scope == "report":
            if component.has_template():
                if unit_scope.translated and not unit_scope.readonly:
                    unit_scope.translate(
                        user,
                        unit_scope.target,
                        STATE_FUZZY,
                        change_action=ActionEvents.MARKED_EDIT,
                    )
            else:
                label = component.project.label_set.get_or_create(
                    name=gettext_noop("Source needs review"), defaults={"color": "red"}
                )[0]
                unit_scope.labels.add(label)

        return new_comment


class CommentQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("timestamp")


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

    def __str__(self) -> str:
        return "comment for {} by {}".format(
            self.unit, self.user.username if self.user else "unknown"
        )

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

    def delete(self, user=None, using=None, keep_parents=False) -> None:
        self.unit.change_set.create(
            action=ActionEvents.COMMENT_DELETE,
            user=user,
            author=self.user,
            details={"comment": self.comment},
        )
        super().delete(using=using, keep_parents=keep_parents)
