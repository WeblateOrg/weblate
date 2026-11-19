# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Populate vulnerable automatic translation audit snapshots before upgrading."""

from __future__ import annotations

from django.apps import apps

Change = apps.get_model("trans", "Change")

Change.objects.create(
    action=61,
    target="weblate.autotranslate.autotranslate",
    details={
        "schema": "weblate-addon-configuration-v1",
        "configuration": {"component": 123, "mode": "suggest"},
        "changed_fields": ["component"],
        "redacted_fields": [],
    },
)
Change.objects.create(
    action=60,
    target="weblate.autotranslate.autotranslate",
    details={"component": 456, "mode": "suggest"},
)
