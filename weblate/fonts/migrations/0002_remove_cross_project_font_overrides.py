# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations, models

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def remove_cross_project_font_overrides(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    font_override = apps.get_model("fonts", "FontOverride")
    font_override.objects.exclude(
        font__project_id=models.F("group__project_id")
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("fonts", "0001_squashed_weblate_5")]

    operations = [
        migrations.RunPython(
            remove_cross_project_font_overrides, migrations.RunPython.noop
        )
    ]
