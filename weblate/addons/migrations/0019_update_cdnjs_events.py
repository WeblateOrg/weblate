# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations

from weblate.addons.events import AddonEvent
from weblate.addons.utils import adjust_addon_events


def update_cdnjs_events(apps, schema_editor) -> None:
    adjust_addon_events(
        apps,
        schema_editor,
        ["weblate.cdn.cdnjs"],
        [
            AddonEvent.EVENT_POST_REMOVE,
            AddonEvent.EVENT_POST_UPDATE,
        ],
        [AddonEvent.EVENT_COMPONENT_UPDATE],
    )


class Migration(migrations.Migration):
    dependencies = [
        ("addons", "0018_migrate_cleanup_settings"),
    ]

    operations = [
        migrations.RunPython(
            update_cdnjs_events,
            migrations.RunPython.noop,
            elidable=True,
        ),
    ]
