# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations


def scrub_addon_change_details(apps, schema_editor) -> None:
    Change = apps.get_model("trans", "Change")
    Change.objects.using(schema_editor.connection.alias).filter(
        action__in=(60, 61, 62)
    ).update(details={})


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0097_workflowsetting_restrict_direct_editing"),
    ]

    operations = [
        migrations.RunPython(
            scrub_addon_change_details,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
