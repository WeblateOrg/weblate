#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Announcement model."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from weblate.lang.models import Language


class AnnouncementManager(models.Manager):
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
            action=Change.ACTION_ANNOUNCEMENT,
            project=result.project,
            component=result.component,
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
        "Project",
        verbose_name=gettext_lazy("Project"),
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    component = models.ForeignKey(
        "Component",
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
    category = models.CharField(
        max_length=25,
        verbose_name=gettext_lazy("Category"),
        help_text=gettext_lazy("Category defines color used for the message."),
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
        default=True,
        verbose_name=gettext_lazy("Notify users"),
    )

    objects = AnnouncementManager.from_queryset(AnnouncementQuerySet)()

    class Meta:
        app_label = "trans"
        verbose_name = gettext_lazy("Announcement")
        verbose_name_plural = gettext_lazy("Announcements")

    def __str__(self):
        return self.message

    def clean(self):
        if self.project and self.component and self.component.project != self.project:
            raise ValidationError(_("Do not specify both component and project!"))
        if not self.project and self.component:
            self.project = self.component.project
