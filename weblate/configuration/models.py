# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Any

from django.db import models


class SettingQuerySet(models.QuerySet):
    def get_settings_dict(self, category: int) -> dict[str, Any]:
        return dict(self.filter(category=category).values_list("name", "value"))


class SettingCategory(models.IntegerChoices):
    UI = 1, "User Interface"
    MT = 2, "Machine Translation"


class Setting(models.Model):
    category = models.IntegerField(choices=SettingCategory)
    name = models.CharField(max_length=100)
    value = models.JSONField()

    objects = SettingQuerySet.as_manager()

    class Meta:
        unique_together = [("category", "name")]
        verbose_name = "Setting"
        verbose_name_plural = "Settings"

    def __str__(self) -> str:
        return f"{self.get_category_display()}:{self.name}:{self.value}"
