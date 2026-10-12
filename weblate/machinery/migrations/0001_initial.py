# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("trans", "0117_change_addon_redact_automation_workflow"),
        ("workspaces", "0006_workspace_enforced_checks"),
    ]

    operations = [
        migrations.CreateModel(
            name="MachineryInstallation",
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
                ("engine", models.CharField(max_length=100)),
                ("slug", models.SlugField(blank=True, max_length=100)),
                ("configuration", models.JSONField(blank=True, default=dict)),
                ("enabled", models.BooleanField(default=True)),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="trans.project",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="workspaces.workspace",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MachineryExclusion",
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
                ("engine", models.CharField(blank=True, max_length=100)),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="trans.project",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="workspaces.workspace",
                    ),
                ),
                (
                    "installation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="machinery.machineryinstallation",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="machineryinstallation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("workspace__isnull", True),
                    ("project__isnull", True),
                    _connector="OR",
                ),
                name="machinery_one_scope",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineryinstallation",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("project__isnull", True),
                    ("slug__gt", ""),
                    ("workspace__isnull", True),
                ),
                fields=("slug",),
                name="machinery_site_slug",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineryinstallation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("slug__gt", ""), ("workspace__isnull", False)),
                fields=("workspace", "slug"),
                name="machinery_workspace_slug",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineryinstallation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("project__isnull", False), ("slug__gt", "")),
                fields=("project", "slug"),
                name="machinery_project_slug",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineryexclusion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("workspace__isnull", True), ("project__isnull", False)),
                    models.Q(("workspace__isnull", False), ("project__isnull", True)),
                    _connector="OR",
                ),
                name="machinery_exclusion_one_scope",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineryexclusion",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("installation__isnull", True),
                        models.Q(("engine", ""), _negated=True),
                    ),
                    models.Q(("installation__isnull", False), ("engine", "")),
                    _connector="OR",
                ),
                name="machinery_exclusion_one_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineryexclusion",
            constraint=models.UniqueConstraint(
                fields=("workspace", "installation"),
                name="machinery_workspace_installation_exclusion",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineryexclusion",
            constraint=models.UniqueConstraint(
                fields=("project", "installation"),
                name="machinery_project_installation_exclusion",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineryexclusion",
            constraint=models.UniqueConstraint(
                condition=models.Q(("engine", ""), _negated=True),
                fields=("workspace", "engine"),
                name="machinery_workspace_engine_exclusion",
            ),
        ),
        migrations.AddConstraint(
            model_name="machineryexclusion",
            constraint=models.UniqueConstraint(
                condition=models.Q(("engine", ""), _negated=True),
                fields=("project", "engine"),
                name="machinery_project_engine_exclusion",
            ),
        ),
    ]
