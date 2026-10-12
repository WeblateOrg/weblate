# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Populate a vulnerable Automation audit snapshot before upgrading."""

from __future__ import annotations

from django.apps import apps

Change = apps.get_model("trans", "Change")

Change.objects.create(
    action=61,
    target="weblate.automation.automation",
    details={
        "schema": "weblate-addon-configuration-v1",
        "configuration": {
            "workflow": {
                "version": 1,
                "triggers": [],
                "actions": [
                    {
                        "action": "weblate.automatic_translation",
                        "settings": {"component": 123},
                    }
                ],
            }
        },
        "changed_fields": ["workflow"],
        "redacted_fields": [],
    },
)
