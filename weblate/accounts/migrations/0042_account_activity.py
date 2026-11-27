# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0041_restricted_team_audit"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountActivity",
            fields=[
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="activity_state",
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("last_activity", models.DateTimeField(null=True)),
                ("removal_at", models.DateTimeField(null=True)),
                ("reminded", models.BooleanField(default=False)),
            ],
        ),
    ]
