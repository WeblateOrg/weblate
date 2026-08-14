# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations

BATCH_SIZE = 1000
SENSITIVE_CONFIGURATION_FIELDS = {
    "weblate.fedora_messaging.publish": frozenset(
        {"amqp_url", "ca_cert", "client_cert", "client_key"}
    ),
    "weblate.webhook.slack": frozenset({"webhook_url"}),
    "weblate.webhook.webhook": frozenset({"secret", "webhook_url"}),
}


def scrub_addon_change_details(apps, schema_editor) -> None:
    Change = apps.get_model("trans", "Change")
    database = schema_editor.connection.alias
    changes = (
        Change.objects.using(database)
        .filter(
            action__in=(60, 61, 62),
            target__in=SENSITIVE_CONFIGURATION_FIELDS,
        )
        .only("details", "target")
        .iterator(chunk_size=BATCH_SIZE)
    )
    updates = []
    for change in changes:
        if type(change.details) is not dict:
            continue
        details = change.details.copy()
        changed = False
        for field in SENSITIVE_CONFIGURATION_FIELDS[change.target]:
            if field in details and details[field] is not None:
                details[field] = None
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
        ("trans", "0097_workflowsetting_restrict_direct_editing"),
    ]

    operations = [
        migrations.RunPython(
            scrub_addon_change_details,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
