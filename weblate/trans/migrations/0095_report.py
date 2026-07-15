# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("trans", "0094_alert_lifecycle"),
        ("workspaces", "0003_workspace_translation_memory"),
    ]

    operations = [
        migrations.CreateModel(
            name="Report",
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
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("credits", "Credits"),
                            ("contributor_stats", "Contributor stats"),
                            ("cost_estimate", "Cost estimate"),
                            ("translator_work", "Translator work analysis"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("version", models.PositiveSmallIntegerField(default=1)),
                ("parameters", models.JSONField(default=dict)),
                ("data", models.JSONField(default=dict)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reports",
                        to="trans.category",
                    ),
                ),
                (
                    "component",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reports",
                        to="trans.component",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="generated_reports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reports",
                        to="trans.project",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reports",
                        to="workspaces.workspace",
                    ),
                ),
            ],
            options={"ordering": ("-created", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="report",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("category__isnull", True),
                        ("component__isnull", True),
                        ("project__isnull", True),
                        ("workspace__isnull", True),
                    )
                    | models.Q(
                        ("category__isnull", True),
                        ("component__isnull", True),
                        ("project__isnull", True),
                        ("workspace__isnull", False),
                    )
                    | models.Q(
                        ("category__isnull", True),
                        ("component__isnull", True),
                        ("project__isnull", False),
                        ("workspace__isnull", True),
                    )
                    | models.Q(
                        ("category__isnull", False),
                        ("component__isnull", True),
                        ("project__isnull", True),
                        ("workspace__isnull", True),
                    )
                    | models.Q(
                        ("category__isnull", True),
                        ("component__isnull", False),
                        ("project__isnull", True),
                        ("workspace__isnull", True),
                    )
                ),
                name="trans_report_single_scope",
            ),
        ),
    ]
