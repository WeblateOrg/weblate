# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def normalize_workspace_team_language_selection(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("weblate_auth", "Group")

    groups = Group.objects.using(db_alias).filter(defining_workspace__isnull=False)
    group_ids = list(groups.values_list("id", flat=True))
    groups.update(language_selection=1)
    if group_ids:
        Group.languages.through.objects.using(db_alias).filter(
            group_id__in=group_ids
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("weblate_auth", "0011_workspace_groups"),
    ]

    operations = [
        migrations.RunPython(
            normalize_workspace_team_language_selection, migrations.RunPython.noop
        ),
    ]
