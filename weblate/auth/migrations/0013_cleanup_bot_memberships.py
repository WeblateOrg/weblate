# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def cleanup_bot_memberships(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    db_alias = schema_editor.connection.alias
    User = apps.get_model("weblate_auth", "User")
    TeamMembership = apps.get_model("weblate_auth", "TeamMembership")

    project_token_ids = (
        User.objects.using(db_alias)
        .filter(
            is_bot=True,
            username__startswith="bot-",
            email__endswith="@bots.noreply.weblate.org",
        )
        .exclude(username__contains=":")
        .values_list("pk", flat=True)
    )
    TeamMembership.objects.using(db_alias).filter(
        user_id__in=project_token_ids,
        group__defining_project__isnull=True,
    ).delete()

    internal_bot_ids = (
        User.objects.using(db_alias)
        .filter(is_bot=True, is_active=False, username__contains=":")
        .values_list("pk", flat=True)
    )
    TeamMembership.objects.using(db_alias).filter(user_id__in=internal_bot_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("weblate_auth", "0012_workspace_team_language_selection"),
    ]

    operations = [
        migrations.RunPython(cleanup_bot_memberships, migrations.RunPython.noop),
    ]
