# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("oauth2_provider", "0022_refreshtoken_token_family_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="IDTokenAuthentication",
            fields=[
                (
                    "id_token",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        serialize=False,
                        to="oauth2_provider.idtoken",
                        swappable=False,
                    ),
                ),
                ("auth_time", models.PositiveBigIntegerField(null=True)),
            ],
        ),
    ]
