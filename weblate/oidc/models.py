# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import models


class IDTokenAuthentication(models.Model):
    """Internal authentication provenance retained while refresh tokens live."""

    id_token = models.OneToOneField(
        "oauth2_provider.IDToken",
        on_delete=models.CASCADE,
        primary_key=True,
        swappable=False,
    )
    auth_time = models.PositiveBigIntegerField(null=True)

    def __str__(self) -> str:
        return f"{self.id_token_id}: {self.auth_time}"
