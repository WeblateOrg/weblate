# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations


def backfill_change_workspace(apps, schema_editor) -> None:
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE trans_change AS change
               SET workspace_id = project.workspace_id
              FROM trans_project AS project
             WHERE change.workspace_id IS NULL
               AND change.project_id = project.id
               AND project.workspace_id IS NOT NULL
            """
        )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("trans", "0087_consolidate_category_inherited_settings"),
    ]

    operations = [
        migrations.RunPython(backfill_change_workspace, migrations.RunPython.noop),
    ]
