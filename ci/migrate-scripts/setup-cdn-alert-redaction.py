# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Seed CDN errors across the three historical storage locations."""

from __future__ import annotations

from django.apps import apps

Addon = apps.get_model("addons", "Addon")
Activity = apps.get_model("addons", "AddonActivityLog")
Alert = apps.get_model("trans", "Alert")
Change = apps.get_model("trans", "Change")
User = apps.get_model("weblate_auth", "User")

remote = {
    "filename": "HtTpS://migration.example/test?secret=cdn-token",
    "error": "Could not fetch cdn-token",
}
local = {"filename": "docs/local.html", "error": "Missing file"}
details = {"occurrences": [remote, local]}
[addon] = Addon.objects.bulk_create(
    [
        Addon(
            component_id=1,
            name="weblate.cdn.cdnjs",
            configuration={"files": remote["filename"]},
        )
    ]
)
Alert.objects.bulk_create(
    [Alert(component_id=1, name="CDNAddonError", details=details)]
)
user, _ = User.objects.get_or_create(username="cdn-migration-manager")
Change.objects.bulk_create(
    [
        Change(
            component_id=1,
            user=user,
            action=103,
            details={"alert": "CDNAddonError", "alert_snapshot": {"details": details}},
        )
    ]
)
Activity.objects.create(
    addon=addon,
    event=1,
    details={
        "result": {
            "results": [
                [remote, local],
                [{**remote, "error": "Translation text too long"}],
            ]
        }
    },
)
