# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def assign_visibility_roles(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    alias = schema_editor.connection.alias
    Group = apps.get_model("weblate_auth", "Group")
    Role = apps.get_model("weblate_auth", "Role")
    for name, roles in (
        ("Users", ("Discover users", "View user profiles")),
        ("Guests", ("View user profiles",)),
    ):
        for team in Group.objects.using(alias).filter(
            name=name, internal=True, defining_project=None, defining_workspace=None
        ):
            team.roles.add(*Role.objects.using(alias).filter(name__in=roles))


class Migration(migrations.Migration):
    dependencies = [("weblate_auth", "0015_update_builtin_roles")]

    operations = [migrations.RunPython(assign_visibility_roles)]
