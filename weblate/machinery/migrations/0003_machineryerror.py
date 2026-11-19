# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("machinery", "0002_import_settings"),
    ]

    operations = [
        migrations.CreateModel(
            name="MachineryError",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "timestamp",
                    models.DateTimeField(
                        db_index=True, default=django.utils.timezone.now
                    ),
                ),
                ("error", models.TextField()),
                (
                    "installation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="machinery.machineryinstallation",
                    ),
                ),
            ],
            options={
                "verbose_name": "machinery error",
                "verbose_name_plural": "machinery errors",
                "ordering": ["-timestamp", "-pk"],
                "indexes": [
                    models.Index(
                        fields=["installation", "-timestamp", "-id"],
                        name="machinery_m_install_ec7c4c_idx",
                    )
                ],
            },
        ),
    ]
