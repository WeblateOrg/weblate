# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify vulnerable Automation audit snapshots were redacted on upgrade."""

from __future__ import annotations

from django.apps import apps

Change = apps.get_model("trans", "Change")

change = Change.objects.get(action=61, target="weblate.automation.automation")
assert change.addon_id is None
assert change.details == {
    "schema": "weblate-addon-configuration-v1",
    "configuration": {"workflow": None},
    "changed_fields": ["workflow"],
    "redacted_fields": ["workflow"],
}
