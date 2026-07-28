# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0004_workspace_metric_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="enforced_checks",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of checks which can not be dismissed.",
                verbose_name="Enforced checks",
            ),
        ),
        migrations.AddField(
            model_name="workspace",
            name="inherit_enforced_checks",
            field=models.BooleanField(
                default=False,
                help_text="Not applicable for workspaces.",
                verbose_name="Inherit enforced checks",
            ),
        ),
    ]
