# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations


def migrate_owners_to_workspace(apps, schema_editor) -> None:
    db_alias = schema_editor.connection.alias
    Billing = apps.get_model("billing", "Billing")
    Group = apps.get_model("weblate_auth", "Group")
    TeamMembership = apps.get_model("weblate_auth", "TeamMembership")

    for billing in Billing.objects.using(db_alias).all():
        owners, _created = Group.objects.using(db_alias).get_or_create(
            defining_workspace_id=billing.workspace_id,
            name="Owners",
            defaults={
                "internal": True,
                "project_selection": 0,
                "language_selection": 1,
            },
        )
        for user_id in (
            billing.owners.all().using(db_alias).values_list("id", flat=True)
        ):
            TeamMembership.objects.using(db_alias).get_or_create(
                user_id=user_id, group_id=owners.pk
            )


class Migration(migrations.Migration):
    dependencies = [
        ("weblate_auth", "0011_workspace_groups"),
        ("billing", "0011_workspace"),
    ]

    operations = [
        migrations.RunPython(
            migrate_owners_to_workspace, migrations.RunPython.noop, elidable=True
        ),
        migrations.RemoveField(
            model_name="billing",
            name="owners",
        ),
    ]
