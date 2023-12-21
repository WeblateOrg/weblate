# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import models
from django.utils.html import format_html
from django.utils.translation import gettext_lazy

from weblate.checks.flags import Flags
from weblate.utils.colors import COLOR_CHOICES

TRANSLATION_LABELS = {"Automatically translated"}


class Label(models.Model):
    project = models.ForeignKey(
        "Project", on_delete=models.deletion.CASCADE, db_index=False
    )
    name = models.CharField(verbose_name=gettext_lazy("Label name"), max_length=190)
    color = models.CharField(
        verbose_name=gettext_lazy("Color"),
        max_length=30,
        choices=COLOR_CHOICES,
        blank=False,
        default=None,
    )

    class Meta:
        app_label = "trans"
        unique_together = [("project", "name")]
        verbose_name = "label"
        verbose_name_plural = "label"

    def __str__(self):
        return format_html(
            '<span class="label label-{}">{}</span>', self.color, self.name
        )

    @property
    def filter_name(self):
        return f"label:{Flags.format_value(self.name)}"
