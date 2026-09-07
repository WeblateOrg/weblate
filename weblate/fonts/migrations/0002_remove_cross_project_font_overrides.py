# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


def remove_cross_project_font_overrides(apps, schema_editor) -> None:
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
