# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Generated manually
from django.db import migrations, models


def set_inherit_enforced_checks(apps, schema_editor):
    Component = apps.get_model("trans", "Component")
    # Components with custom enforced_checks should not inherit
    Component.objects.exclude(enforced_checks=[]).update(inherit_enforced_checks=False)
    # Components with empty enforced_checks (default) should inherit
    Component.objects.filter(enforced_checks=[]).update(inherit_enforced_checks=True)


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0096_change_recent_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="component",
            name="inherit_enforced_checks",
            field=models.BooleanField(
                default=True,
                verbose_name="Inherit enforced checks",
                help_text="Use enforced checks from the project, category or workspace.",
            ),
        ),
        migrations.RunPython(
            set_inherit_enforced_checks, reverse_code=migrations.RunPython.noop
        ),
    ]
