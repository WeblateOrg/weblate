# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Any

from weblate.addons.automation_operations import OPERATIONS, object_schema
from weblate.addons.events import AddonEvent
from weblate.trans.actions import ActionEvents
from weblate.utils.state import StringState

TRIGGERS = {
    "change": AddonEvent.EVENT_CHANGE,
    "daily": AddonEvent.EVENT_DAILY,
    "component_update": AddonEvent.EVENT_COMPONENT_UPDATE,
    "post_update": AddonEvent.EVENT_POST_UPDATE,
    "post_commit": AddonEvent.EVENT_POST_COMMIT,
    "post_push": AddonEvent.EVENT_POST_PUSH,
    "manual": AddonEvent.EVENT_MANUAL,
}
CHANGE_ACTIONS = {action.name.lower(): action.value for action in ActionEvents}


STRING = {"type": "string", "maxLength": 4096}
CONDITIONS = {"type": "array", "items": {"$ref": "#/$defs/condition"}, "maxItems": 100}
ACTIONS = {"type": "array", "items": {"$ref": "#/$defs/action"}, "maxItems": 100}


def action_schema(
    name: str, title: str, added: str, settings: dict[str, Any]
) -> dict[str, Any]:
    return object_schema(
        {
            "action": {"const": name},
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
            "settings": settings,
        },
        ["action", "settings"],
    ) | {"title": title, "x-version-added": added}


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$comment": "Generated from weblate.addons.automation_schema.SCHEMA using make -C docs update-automation-schema.",
    "title": "Workflow definition",
    "x-version-added": "2026.10",
    **object_schema(
        {
            "version": {"const": 1},
            "triggers": {
                "type": "array",
                "maxItems": 100,
                "uniqueItems": True,
                "items": {
                    "oneOf": [
                        object_schema(
                            {
                                "trigger": {
                                    "enum": [
                                        name for name in TRIGGERS if name != "change"
                                    ]
                                }
                            },
                            ["trigger"],
                        ),
                        object_schema(
                            {
                                "trigger": {"const": "change"},
                                "events": {
                                    "type": "array",
                                    "items": {"enum": list(CHANGE_ACTIONS)},
                                    "minItems": 1,
                                    "uniqueItems": True,
                                },
                            },
                            ["trigger", "events"],
                        ),
                    ]
                },
            },
            "conditions": CONDITIONS,
            "actions": ACTIONS,
        },
        ["version", "triggers", "actions"],
    ),
    "$defs": {
        "condition": {
            "oneOf": [
                object_schema(
                    {
                        "condition": {
                            "enum": [
                                "expression",
                                "component_category",
                                "language",
                                "matching_strings",
                            ]
                        },
                        "value": STRING,
                    },
                    ["condition", "value"],
                ),
                object_schema(
                    {
                        "condition": {"const": "change_action"},
                        "value": {"enum": list(CHANGE_ACTIONS)},
                    },
                    ["condition", "value"],
                ),
                object_schema(
                    {
                        "condition": {"const": "unit_state"},
                        "value": {"enum": list(StringState.values)},
                    },
                    ["condition", "value"],
                ),
                object_schema(
                    {
                        "condition": {"enum": ["and", "or", "not"]},
                        "conditions": CONDITIONS,
                    },
                    ["condition", "conditions"],
                ),
            ]
        },
        "action": {
            "oneOf": [
                *[
                    action_schema(
                        operation.name,
                        operation.title,
                        operation.version_added,
                        operation.settings_schema,
                    )
                    for operation in OPERATIONS.values()
                ],
                object_schema({"sequence": ACTIONS}, ["sequence"])
                | {"title": "Sequence", "x-version-added": "2026.10"},
                object_schema(
                    {
                        "choose": {
                            "type": "array",
                            "maxItems": 100,
                            "items": object_schema(
                                {"conditions": CONDITIONS, "sequence": ACTIONS},
                                ["conditions", "sequence"],
                            ),
                        },
                        "default": ACTIONS,
                    },
                    ["choose"],
                )
                | {"title": "Choose", "x-version-added": "2026.10"},
            ]
        },
    },
}
