# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from importlib import import_module
from itertools import batched
from typing import TYPE_CHECKING

from django.db import migrations

from weblate.utils.hash import calculate_json_fingerprint

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


BATCH_SIZE = 1000
ALERT_COMMANDS = {
    "AddonScriptError": "Script",
    "MsgmergeAddonError": "msgmerge",
    "ExtractPotAddonError": "Gettext extraction",
}


def redact_occurrences(name: str, details: object) -> bool:
    if not isinstance(details, dict) or not isinstance(
        occurrences := details.get("occurrences"), list
    ):
        return False
    changed = False
    for occurrence in occurrences:
        if not isinstance(occurrence, dict):
            continue
        # Legacy process diagnostics are unstructured, even when they contain no path.
        error = occurrence.get("error")
        if error != "Template for new translations not found":
            error = "Command failed"
        safe = {"command": ALERT_COMMANDS[name], "output": "", "error": error}
        if any(occurrence.get(key) != value for key, value in safe.items()):
            occurrence.update(safe)
            changed = True
    return changed


def redact_process_paths(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    database = schema_editor.connection.alias
    alerts = apps.get_model("trans", "Alert").objects.using(database)
    changes = apps.get_model("trans", "Change").objects.using(database)
    dismissal_context = import_module(
        "weblate.trans.migrations.0094_alert_lifecycle"
    ).get_addon_error_context
    rows = alerts.filter(name__in=ALERT_COMMANDS).only(
        "pk", "name", "details", "dismissed_at", "dismissal_fingerprint"
    )
    for batch in batched(rows.iterator(chunk_size=BATCH_SIZE), BATCH_SIZE):
        pending = []
        for alert in batch:
            if redact_occurrences(alert.name, alert.details):
                if alert.dismissed_at is not None:
                    alert.dismissal_fingerprint = calculate_json_fingerprint(
                        dismissal_context(alert.details)
                    )
                pending.append(alert)
        if pending:
            alerts.bulk_update(
                pending, ["details", "dismissal_fingerprint"], batch_size=BATCH_SIZE
            )

    snapshots = changes.filter(
        action=103, details__alert__in=list(ALERT_COMMANDS)
    ).only("pk", "details")
    for batch in batched(snapshots.iterator(chunk_size=BATCH_SIZE), BATCH_SIZE):
        pending = []
        for change in batch:
            snapshot = change.details.get("alert_snapshot")
            if isinstance(snapshot, dict) and redact_occurrences(
                change.details["alert"], snapshot.get("details")
            ):
                pending.append(change)
        if pending:
            changes.bulk_update(pending, ["details"], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):
    dependencies = [
        ("addons", "0023_redact_cdn_remote_sources"),
        ("trans", "0124_case_insensitive_slugs"),
    ]

    operations = [
        migrations.RunPython(redact_process_paths, migrations.RunPython.noop),
    ]
