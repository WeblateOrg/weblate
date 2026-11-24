# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("metrics", "0003_cleanup_category_language_metric_keys"),
        ("trans", "0124_case_insensitive_slugs"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ContributorCollection",
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
                ("collection_date", models.DateField()),
                ("cursor", models.BigIntegerField(default=0)),
                ("last_completed", models.DateField(null=True)),
            ],
        ),
        migrations.CreateModel(
            name="ContributorCount",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("contributions", models.PositiveBigIntegerField()),
                ("edits", models.PositiveBigIntegerField()),
                (
                    "translation",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="trans.translation",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["translation", "-edits", "user"],
                        name="metrics_contributor_rank_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("translation", "user"),
                        name="metrics_contributor_scope_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("edits__lte", models.F("contributions"))),
                        name="metrics_contributor_edits_valid",
                    ),
                ],
            },
        ),
    ]
