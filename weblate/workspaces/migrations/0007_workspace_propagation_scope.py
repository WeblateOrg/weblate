# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0006_workspace_enforced_checks"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="propagation_scope",
            field=models.CharField(
                choices=[
                    ("project", "Project"),
                    ("workspace", "Workspace"),
                    ("component_name", "Matching component name within workspace"),
                ],
                default="project",
                help_text="Where translations of matching strings are propagated.",
                max_length=20,
                verbose_name="Translation propagation scope",
            ),
        ),
    ]
