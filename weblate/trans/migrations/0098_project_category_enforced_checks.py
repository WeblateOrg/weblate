# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0097_component_inherit_enforced_checks"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="enforced_checks",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of checks which can not be dismissed.",
                verbose_name="Enforced checks",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="inherit_enforced_checks",
            field=models.BooleanField(
                default=True,
                help_text="Use enforced checks from the workspace.",
                verbose_name="Inherit enforced checks",
            ),
        ),
        migrations.AddField(
            model_name="category",
            name="enforced_checks",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of checks which can not be dismissed.",
                verbose_name="Enforced checks",
            ),
        ),
        migrations.AddField(
            model_name="category",
            name="inherit_enforced_checks",
            field=models.BooleanField(
                default=True,
                help_text="Use enforced checks from the parent category, project or workspace.",
                verbose_name="Inherit enforced checks",
            ),
        ),
    ]
