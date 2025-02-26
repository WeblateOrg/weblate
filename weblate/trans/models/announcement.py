# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Announcement model."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy

from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents


class AnnouncementManager(models.Manager["Announcement"]):
    def context_filter(self, project=None, component=None, language=None):
        """Filter announcements by context."""
        base = self.filter(
            Q(expiry__isnull=True) | Q(expiry__gte=timezone.now())
        ).order()

        if language and project is None and component is None:
            return base.filter(project=None, component=None, language=language)

        if component:
            if language:
                return base.filter(
                    (Q(component=component) & Q(language=language))
                    | (Q(component=None) & Q(language=language))
                    | (Q(component=component) & Q(language=None))
                    | (Q(project=component.project) & Q(component=None))
                )

            return base.filter(
                (Q(component=component) & Q(language=None))
                | (Q(project=component.project) & Q(component=None))
            )

        if project:
            return base.filter(Q(project=project) & Q(component=None))

        # All are None
        return base.filter(project=None, component=None, language=None)

    def create(self, user=None, **kwargs):
        from weblate.trans.models.change import Change

        result = super().create(**kwargs)

        Change.objects.create(
            action=ActionEvents.ANNOUNCEMENT,
            project=result.project,
            category=result.category,
            component=result.component,
            language=result.language,
            announcement=result,
            target=result.message,
            user=user,
        )
        return result


class AnnouncementQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("id")


class Announcement(models.Model):
    message = models.TextField(
        verbose_name=gettext_lazy("Message"),
        help_text=gettext_lazy("You can use Markdown and mention users by @username."),
    )
    project = models.ForeignKey(
        "trans.Project",
        verbose_name=gettext_lazy("Project"),
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    category = models.ForeignKey(
        "trans.Category",
        verbose_name=gettext_lazy("Category"),
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    component = models.ForeignKey(
        "trans.Component",
        verbose_name=gettext_lazy("Component"),
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    language = models.ForeignKey(
        Language,
        verbose_name=gettext_lazy("Language"),
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    severity = models.CharField(
        max_length=25,
        verbose_name=gettext_lazy("Severity"),
        help_text=gettext_lazy("Severity defines color used for the message."),
        choices=(
            ("info", gettext_lazy("Info (light blue)")),
            ("warning", gettext_lazy("Warning (yellow)")),
            ("danger", gettext_lazy("Danger (red)")),
            ("success", gettext_lazy("Success (green)")),
        ),
        default="info",
    )
    expiry = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=gettext_lazy("Expiry date"),
        help_text=gettext_lazy(
            "The message will be not shown after this date. "
            "Use it to announce string freeze and translation "
            "deadline for next release."
        ),
    )
    notify = models.BooleanField(
        blank=True,
        default=False,
        verbose_name=gettext_lazy("Notify users"),
        help_text=gettext_lazy("Send notification to subscribed users."),
    )

    objects = AnnouncementManager.from_queryset(AnnouncementQuerySet)()

    class Meta:
        app_label = "trans"
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"

    def __str__(self) -> str:
        return self.message

    def clean(self) -> None:
        if self.project and self.component and self.component.project != self.project:
            raise ValidationError(gettext("Do not specify both component and project!"))
        if not self.project and self.component:
            self.project = self.component.project
