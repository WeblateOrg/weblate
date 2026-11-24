# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


BATCH_SIZE = 1000


def redact_sources(value: object) -> bool:
    if isinstance(value, list):
        changed = False
        for item in value:
            if redact_sources(item):
                changed = True
        return changed
    if not isinstance(value, dict):
        return False
    if "results" in value:
        # Multiple task results stored together in one activity log.
        return redact_sources(value["results"])
    filename = value.get("filename")
    if not isinstance(filename, str) or not filename.lower().startswith(
        ("http://", "https://")
    ):
        return False
    # Historical configuration line numbers are unavailable.
    value["filename"] = "Remote source"
    if value.get("error") != "Translation text too long":
        value["error"] = "Could not read remote source"
    return True


def redact_cdn_records(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    database = schema_editor.connection.alias
    alerts = apps.get_model("trans", "Alert").objects.using(database)
    changes = apps.get_model("trans", "Change").objects.using(database)
    activities = apps.get_model("addons", "AddonActivityLog").objects.using(database)
    for records, path in (
        (alerts.filter(name="CDNAddonError"), ("occurrences",)),
        (
            changes.filter(action=103, details__alert="CDNAddonError"),
            ("alert_snapshot", "details", "occurrences"),
        ),
        (activities.filter(addon__name="weblate.cdn.cdnjs"), ("result",)),
    ):
        pending = []
        for record in records.only("pk", "details").iterator(chunk_size=BATCH_SIZE):
            value = record.details
            for key in path:
                value = value.get(key) if isinstance(value, dict) else None
            if not redact_sources(value):
                continue
            pending.append(record)
            if len(pending) == BATCH_SIZE:
                records.bulk_update(pending, ["details"], batch_size=BATCH_SIZE)
                pending.clear()
        if pending:
            records.bulk_update(pending, ["details"], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):
    dependencies = [
        ("addons", "0022_addonactivitylog_status"),
        ("trans", "0124_case_insensitive_slugs"),
    ]

    operations = [
        migrations.RunPython(redact_cdn_records, migrations.RunPython.noop),
    ]
