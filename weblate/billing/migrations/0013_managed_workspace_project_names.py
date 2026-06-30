# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import DEFAULT_DB_ALIAS, migrations

WORKSPACE_NAME_LENGTH = 100


def rename_single_project_billing_workspaces(apps, schema_editor) -> None:
    Billing = apps.get_model("billing", "Billing")
    Project = apps.get_model("trans", "Project")
    Workspace = apps.get_model("workspaces", "Workspace")

    db_alias = (
        schema_editor.connection.alias
        if schema_editor is not None
        else DEFAULT_DB_ALIAS
    )
    workspace_ids = (
        Billing.objects.using(db_alias)
        .filter(customer_name="", workspace__name_managed=True)
        .values_list("workspace_id", flat=True)
    )

    for workspace_id in workspace_ids.iterator():
        project_names = list(
            Project.objects.using(db_alias)
            .filter(workspace_id=workspace_id)
            .order_by("id")
            .values_list("name", flat=True)[:2]
        )
        if len(project_names) != 1:
            continue

        name = project_names[0][:WORKSPACE_NAME_LENGTH]
        Workspace.objects.using(db_alias).filter(
            pk=workspace_id, name_managed=True
        ).exclude(name=name).update(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0012_migrate_owners_to_workspace"),
    ]

    operations = [
        migrations.RunPython(
            rename_single_project_billing_workspaces, migrations.RunPython.noop
        ),
    ]
