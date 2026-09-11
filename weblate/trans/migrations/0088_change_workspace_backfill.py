# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def backfill_change_workspace(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Change = apps.get_model("trans", "Change")
    Project = apps.get_model("trans", "Project")

    for project_id, workspace_id in (
        Project.objects.filter(workspace__isnull=False)
        .values_list("id", "workspace_id")
        .iterator()
    ):
        Change.objects.filter(
            workspace__isnull=True,
            project_id=project_id,
        ).update(workspace_id=workspace_id)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("trans", "0087_consolidate_category_inherited_settings"),
    ]

    operations = [
        migrations.RunPython(backfill_change_workspace, migrations.RunPython.noop),
    ]
