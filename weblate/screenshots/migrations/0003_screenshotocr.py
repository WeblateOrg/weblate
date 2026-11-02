# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("screenshots", "0002_repair_image_extensions"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScreenshotOCR",
            fields=[
                (
                    "screenshot",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="ocr_cache",
                        serialize=False,
                        to="screenshots.screenshot",
                    ),
                ),
                ("signature", models.JSONField(default=dict)),
                ("generation", models.UUIDField(default=uuid.uuid4)),
                ("data", models.JSONField(null=True)),
                ("task_id", models.UUIDField(null=True)),
                ("requested_at", models.DateTimeField(null=True)),
                ("error", models.CharField(blank=True, max_length=16)),
            ],
        ),
    ]
