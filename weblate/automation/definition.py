# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from jsonschema import Draft202012Validator
from ruamel.yaml import YAML, YAMLError
from ruamel.yaml.tokens import AliasToken, TagToken

from weblate.automation.expressions import expressions
from weblate.automation.schema import SCHEMA

if TYPE_CHECKING:
    from collections.abc import Iterator


def walk(
    value: object, path: str = "workflow", depth: int = 0
) -> Iterator[tuple[str, dict[str, Any]]]:
    if depth > 32:
        raise ValidationError(gettext("Automation nesting is too deep."))
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from walk(item, f"{path}.{key}", depth + 1)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, f"{path}[{index}]", depth + 1)


def validate_workflow_size(value: object) -> None:
    """Apply the execution limit to the serialized, normalized definition."""
    if len(json.dumps(value, allow_nan=False).encode()) > 65536:
        raise ValidationError(gettext("Automation definitions cannot exceed 64 KiB."))


def parse_workflow(value: object) -> dict[str, Any]:
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        text = value if isinstance(value, str) else json.dumps(value, allow_nan=False)
        if len(text.encode()) > 65536:
            raise ValidationError(
                gettext("Automation definitions cannot exceed 64 KiB.")
            )
        yaml = YAML(typ="safe", pure=True)
        if any(isinstance(token, (AliasToken, TagToken)) for token in yaml.scan(text)):
            raise ValidationError(gettext("YAML aliases and tags are not supported."))
        result = yaml.load(text)
        # Enforce JSON types, reject timestamps, recursive input and non-string keys.
        nodes = list(walk(result))
        if any(not isinstance(key, str) for _, node in nodes for key in node):
            raise ValidationError(gettext("Automation keys must be strings."))
        validate_workflow_size(result)
    except (YAMLError, ValueError, TypeError, RecursionError) as error:
        raise ValidationError(gettext("Invalid automation YAML or JSON.")) from error
    errors = list(Draft202012Validator(SCHEMA).iter_errors(result))
    if errors:
        validation_error = errors[0]
        path = (
            ".".join(str(part) for part in validation_error.absolute_path) or "workflow"
        )
        raise ValidationError(
            gettext("%(path)s: %(error)s")
            % {"path": path, "error": validation_error.message[:1024]}
        )
    count = sum(
        "condition" in node
        or any(key in node for key in ("action", "choose", "sequence"))
        for _, node in nodes
    )
    if count > 100 or any(
        path.count(".sequence")
        + path.count(".conditions")
        + path.count(".default")
        + path.count(".choose")
        > 8
        for path, _ in nodes
    ):
        raise ValidationError(
            gettext("Automation exceeds 100 nodes or eight nesting levels.")
        )
    ids = [node["id"] for _, node in nodes if "action" in node and "id" in node]
    if len(ids) != len(set(ids)):
        raise ValidationError(gettext("Automation action IDs must be unique."))
    seen_ids: set[str] = set()
    for path, node in nodes:
        if "action" not in node:
            continue
        scope = node.get("scope", "component")
        if scope == "trigger" and (
            not result["triggers"]
            or any(trigger["trigger"] != "change" for trigger in result["triggers"])
        ):
            raise ValidationError(
                gettext("%(path)s: trigger scope requires only change triggers.")
                % {"path": path}
            )
        if scope.startswith("result:") and scope[7:] not in seen_ids:
            raise ValidationError(
                gettext("%(path)s: result scope requires an earlier action ID.")
                % {"path": path}
            )
        if "id" in node:
            seen_ids.add(node["id"])
    for path, node in nodes:
        if node.get("condition") == "not" and len(node["conditions"]) != 1:
            raise ValidationError(
                gettext("%(path)s: not requires exactly one condition.")
                % {"path": path}
            )
    expressions(
        [node["value"] for _, node in nodes if node.get("condition") == "expression"]
    )
    return result
