# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify persisted CDN errors are scrubbed without changing local diagnostics."""

from __future__ import annotations

from django.apps import apps

Alert = apps.get_model("trans", "Alert")
Change = apps.get_model("trans", "Change")
Activity = apps.get_model("addons", "AddonActivityLog")
remote = {"filename": "Remote source", "error": "Could not read remote source"}
local = {"filename": "docs/local.html", "error": "Missing file"}
alert = Alert.objects.get(component_id=1, name="CDNAddonError")
assert alert.details == {"occurrences": [remote, local]}
assert alert.dismissed_at is None
change = Change.objects.get(action=103, user__username="cdn-migration-manager")
assert change.details["alert"] == "CDNAddonError"
assert change.details["alert_snapshot"] == {"details": alert.details}
activity = Activity.objects.get(
    addon__component_id=1, addon__name="weblate.cdn.cdnjs", event=1
)
assert activity.details == {
    "result": {
        "results": [[remote, local], [{**remote, "error": "Translation text too long"}]]
    }
}
assert activity.addon.configuration == {
    "files": "HtTpS://migration.example/test?secret=cdn-token"
}
