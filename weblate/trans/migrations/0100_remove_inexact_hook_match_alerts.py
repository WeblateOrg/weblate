# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def remove_inexact_hook_match_alerts(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Alert = apps.get_model("trans", "Alert")
    Alert.objects.filter(name="InexactHookMatch").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0099_sanitize_repository_redirect_credentials"),
    ]

    operations = [
        migrations.RunPython(
            remove_inexact_hook_match_alerts,
            migrations.RunPython.noop,
            elidable=True,
        ),
    ]
