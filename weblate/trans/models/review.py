# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from django.conf import settings
from django.db import models


class UnitReview(models.Model):
    unit = models.ForeignKey(
        "trans.Unit",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="unit_reviews",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "trans"
        unique_together = [("unit", "user")]
        verbose_name = "unit review"
        verbose_name_plural = "unit reviews"

    def __str__(self) -> str:
        return f"Review by {self.user} on {self.unit_id}"
