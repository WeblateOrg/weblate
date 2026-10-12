# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

import django.db.models.deletion
from django.db import migrations, models

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


ADDON_ACTIONS = (60, 61, 62)
ADDON_CHANGE_DETAILS_SCHEMA = "weblate-addon-configuration-v1"
AUTOMATION_ADDON = "weblate.automation.automation"
BATCH_SIZE = 1000


def redact_automation_workflows(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Change = apps.get_model("trans", "Change")
    database = schema_editor.connection.alias
    changes = (
        Change.objects.using(database)
        .filter(action__in=ADDON_ACTIONS, target=AUTOMATION_ADDON)
        .only("details")
        .iterator(chunk_size=BATCH_SIZE)
    )
    updates = []
    for change in changes:
        if not isinstance(change.details, dict):
            continue
        details = change.details.copy()
        changed = False
        configuration = details.get("configuration")
        if isinstance(configuration, dict) and "workflow" in configuration:
            configuration = configuration.copy()
            if configuration["workflow"] is not None:
                configuration["workflow"] = None
                changed = True
            details["configuration"] = configuration
            redacted_fields = details.get("redacted_fields")
            if (
                details.get("schema") == ADDON_CHANGE_DETAILS_SCHEMA
                and isinstance(redacted_fields, list)
                and all(isinstance(field, str) for field in redacted_fields)
                and "workflow" not in redacted_fields
            ):
                details["redacted_fields"] = sorted([*redacted_fields, "workflow"])
                changed = True
        if "workflow" in details and details["workflow"] is not None:
            details["workflow"] = None
            changed = True
        if not changed:
            continue
        change.details = details
        updates.append(change)
        if len(updates) == BATCH_SIZE:
            Change.objects.using(database).bulk_update(
                updates, ("details",), batch_size=BATCH_SIZE
            )
            updates.clear()
    if updates:
        Change.objects.using(database).bulk_update(
            updates, ("details",), batch_size=BATCH_SIZE
        )


class Migration(migrations.Migration):
    dependencies = [
        ("addons", "0022_addonactivitylog_status"),
        ("trans", "0116_component_push_on_update"),
    ]

    operations = [
        migrations.AddField(
            model_name="change",
            name="addon",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="addons.addon",
            ),
        ),
        migrations.RunPython(
            redact_automation_workflows, reverse_code=migrations.RunPython.noop
        ),
    ]
