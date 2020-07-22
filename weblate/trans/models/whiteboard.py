# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

"""Whiteboard model."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.html import urlize
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from weblate.lang.models import Language


class WhiteboardManager(models.Manager):
    def context_filter(self, project=None, component=None, language=None):
        """Filter whiteboard messages by context."""
        base = self.filter(Q(expiry__isnull=True) | Q(expiry__gte=timezone.now()))

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


class WhiteboardMessage(models.Model):
    message = models.TextField(verbose_name=gettext_lazy("Message"))
    message_html = models.BooleanField(  # noqa: DJ02
        verbose_name=gettext_lazy("Render as HTML"),
        help_text=gettext_lazy(
            "When turned off, URLs will be converted to links and "
            "any markup will be escaped."
        ),
        blank=True,
        default=False,
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

    objects = WhiteboardManager()

    class Meta:
        app_label = "trans"
        verbose_name = gettext_lazy("Whiteboard message")
        verbose_name_plural = gettext_lazy("Whiteboard messages")

    def __str__(self):
        return self.message

    def save(self, *args, **kwargs):
        is_new = not self.id
        super().save(*args, **kwargs)
        if is_new:
            from weblate.trans.models.change import Change

            Change.objects.create(
                action=Change.ACTION_MESSAGE,
                project=self.project,
                component=self.component,
                whiteboard=self,
                target=self.message,
            )

    def clean(self):
        if self.project and self.component and self.component.project != self.project:
            raise ValidationError(_("Do not specify both component and project!"))
        if not self.project and self.component:
            self.project = self.component.project

    def render(self):
        if self.message_html:
            return mark_safe(self.message)
        return mark_safe(urlize(self.message, autoescape=True))
