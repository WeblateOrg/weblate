# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import models
from django.utils.html import format_html
from django.utils.translation import gettext_lazy

from weblate.checks.flags import Flags
from weblate.utils.colors import ColorChoices

TRANSLATION_LABELS = {"Automatically translated"}


class Label(models.Model):
    project = models.ForeignKey(
        "trans.Project", on_delete=models.deletion.CASCADE, db_index=False
    )
    name = models.CharField(verbose_name=gettext_lazy("Label name"), max_length=190)
    color = models.CharField(
        verbose_name=gettext_lazy("Color"),
        max_length=30,
        choices=ColorChoices.choices,
        blank=False,
        default=None,
    )
    description = models.CharField(
        verbose_name=gettext_lazy("Label description"),
        default="",
        max_length=250,
        blank=True,
    )

    class Meta:
        app_label = "trans"
        unique_together = [("project", "name")]
        verbose_name = "label"
        verbose_name_plural = "label"

    def __str__(self) -> str:
        return format_html(
            '<span class="label label-{}">{}</span>', self.color, self.name
        )

    @property
    def filter_name(self) -> str:
        return f"label:{Flags.format_value(self.name)}"
