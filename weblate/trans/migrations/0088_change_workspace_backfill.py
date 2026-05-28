# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations
from django.db.models import OuterRef, Subquery


def backfill_change_workspace(apps, schema_editor) -> None:
    Change = apps.get_model("trans", "Change")
    Project = apps.get_model("trans", "Project")
    projects_with_workspace = Project.objects.filter(workspace__isnull=False)
    project_workspace = projects_with_workspace.filter(
        pk=OuterRef("project_id")
    ).values("workspace_id")[:1]

    Change.objects.filter(
        workspace__isnull=True,
        project_id__in=projects_with_workspace.values("pk"),
    ).update(workspace_id=Subquery(project_workspace))


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("trans", "0087_consolidate_category_inherited_settings"),
    ]

    operations = [
        migrations.RunPython(backfill_change_workspace, migrations.RunPython.noop),
    ]
