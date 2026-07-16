# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("trans", "0095_report"),
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
                    "engine",
                    models.CharField(db_index=True, max_length=100),
                ),
                (
                    "timestamp",
                    models.DateTimeField(
                        default=django.utils.timezone.now, db_index=True
                    ),
                ),
                ("error", models.TextField()),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="trans.project",
                    ),
                ),
            ],
            options={
                "verbose_name": "Machinery error",
                "verbose_name_plural": "Machinery errors",
                "ordering": ["-timestamp"],
            },
        ),
    ]
