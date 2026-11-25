# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify that the upgrade preserves alert identity and removes process paths."""

from __future__ import annotations

from django.apps import apps

Alert = apps.get_model("trans", "Alert")
Change = apps.get_model("trans", "Change")

for name, command, error in (
    ("MsgmergeAddonError", "msgmerge", "Template for new translations not found"),
    ("ExtractPotAddonError", "Gettext extraction", "Command failed"),
    ("AddonScriptError", "Script", "Command failed"),
):
    expected = {
        "occurrences": [
            {"addon_id": "9", "command": command, "output": "", "error": error},
            {
                "addon_id": "9",
                "command": command,
                "output": "",
                "error": "Command failed",
            },
        ]
    }
    alert = Alert.objects.get(component_id=1, name=name)
    assert alert.details == expected
    if name == "MsgmergeAddonError":
        assert alert.dismissed_at is not None
        assert (
            alert.dismissal_fingerprint
            == alert.alert_class.get_dismissal_fingerprint(alert.component, expected)
        )
    change = Change.objects.get(
        action=103, details__alert=name, user__username="process-migration-manager"
    )
    assert change.details["alert_snapshot"]["details"] == expected
