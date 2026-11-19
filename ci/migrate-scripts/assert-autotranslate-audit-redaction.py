# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify automatic translation audit snapshots were redacted on upgrade."""

from __future__ import annotations

from django.apps import apps

Change = apps.get_model("trans", "Change")
target = "weblate.autotranslate.autotranslate"

versioned = Change.objects.get(action=61, target=target)
assert versioned.details == {
    "schema": "weblate-addon-configuration-v1",
    "configuration": {"component": None, "mode": "suggest"},
    "changed_fields": ["component"],
    "redacted_fields": ["component"],
}
legacy = Change.objects.get(action=60, target=target)
assert legacy.details == {"component": None, "mode": "suggest"}
