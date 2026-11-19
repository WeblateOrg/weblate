# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def clear_github_app_push(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Component = apps.get_model("trans", "Component")
    Component.objects.using(schema_editor.connection.alias).filter(
        vcs="github-app"
    ).exclude(push="", push_branch="").update(push="", push_branch="")


class Migration(migrations.Migration):
    dependencies = [("trans", "0120_change_addon_redact_autotranslate_component")]

    operations = [
        migrations.RunPython(clear_github_app_push, migrations.RunPython.noop),
    ]
