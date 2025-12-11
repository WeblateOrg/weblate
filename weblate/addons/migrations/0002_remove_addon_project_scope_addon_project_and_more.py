# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models


def populate_project_from_component(apps, schema_editor) -> None:
    """Migrate Addons with project_scope from using component to using project."""
    Addon = apps.get_model("addons", "Addon")
    updates = []
    for addon in Addon.objects.filter(project_scope=True):
        addon.project = addon.component.project
        addon.component = None
        updates.append(addon)
        if len(updates) > 1000:
            Addon.objects.bulk_update(updates, ["project", "component"])
            updates = []
    if updates:
        Addon.objects.bulk_update(updates, ["project", "component"])


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0004_alter_change_action"),
        ("addons", "0001_squashed_weblate_5"),
    ]

    operations = [
        migrations.AddField(
            model_name="addon",
            name="project",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="trans.project",
            ),
        ),
        migrations.AlterField(
            model_name="addon",
            name="component",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="trans.component",
            ),
        ),
        migrations.RunPython(populate_project_from_component, elidable=True),
        migrations.RemoveField(
            model_name="addon",
            name="project_scope",
        ),
    ]
