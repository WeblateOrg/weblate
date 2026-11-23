# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Seed historical process diagnostics in live alerts and detached snapshots."""

from __future__ import annotations

from django.apps import apps
from django.utils import timezone

Alert = apps.get_model("trans", "Alert")
Change = apps.get_model("trans", "Change")
User = apps.get_model("weblate_auth", "User")
actor, _ = User.objects.get_or_create(username="process-migration-manager")

for name, command, output, error in (
    (
        "MsgmergeAddonError",
        "msgmerge",
        "/private/templates/base.pot",
        "Template for new translations not found",
    ),
    (
        "ExtractPotAddonError",
        "/private/python /private/runner",
        "/private/source",
        "Command failed: /private/runner",
    ),
    ("AddonScriptError", "script", "/private/script-output", "Command failed"),
):
    details = {
        "occurrences": [
            {"addon_id": "9", "command": command, "output": output, "error": error},
            {
                "addon_id": "9",
                "command": "msgmerge",
                "output": "synthetic sensitive tool output",
                "error": "synthetic sensitive exception",
            },
        ]
    }
    alert = Alert(component_id=1, name=name, details=details)
    if name == "MsgmergeAddonError":
        alert.dismissed_at = timezone.now()
        alert.dismissal_fingerprint = alert.alert_class.get_dismissal_fingerprint(
            alert.component, details
        )
    Alert.objects.bulk_create([alert])
    Change.objects.bulk_create(
        [
            Change(
                component_id=1,
                user=actor,
                action=103,
                details={"alert": name, "alert_snapshot": {"details": details}},
            )
        ]
    )
