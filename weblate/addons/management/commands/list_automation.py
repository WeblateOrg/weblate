# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from weblate.addons.automation_schema import CHANGE_ACTIONS, SCHEMA
from weblate.utils.management.base import DocGeneratorCommand

if TYPE_CHECKING:
    from pathlib import Path


def describe_parameter(schema: dict[str, Any]) -> str:
    """Describe the public JSON Schema without duplicating parameter definitions."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return f"``{json.dumps(schema['const'])}``"
    if "enum" in schema:
        # Event names form a long list; their authoritative reference is shared.
        if schema["enum"] == list(CHANGE_ACTIONS):
            return "Event name from :ref:`change-actions`"
        return ", ".join(f"``{json.dumps(value)}``" for value in schema["enum"])
    kind = schema.get("type", "object")
    if isinstance(kind, list):
        kind = " or ".join(kind)
    elif kind == "array":
        kind = f"List of ({describe_parameter(schema['items'])})"
    limits = [
        f"{label} {schema[key]}"
        for key, label in (
            ("minimum", "minimum"),
            ("maximum", "maximum"),
            ("maxLength", "maximum length"),
            ("minItems", "minimum items"),
            ("maxItems", "maximum items"),
        )
        if key in schema
    ]
    if schema.get("uniqueItems"):
        limits.append("unique items")
    if "pattern" in schema:
        limits.append(f"pattern ``{schema['pattern']}``")
    return "; ".join([kind, *limits])


class Command(DocGeneratorCommand):
    help = "Generate the automation reference from its JSON Schema"

    def document(
        self, name: str, title: str, schema: dict[str, Any], *, level: str = "~"
    ) -> None:
        lines = [f".. _automation-{name}:", "", title, level * len(title), ""]
        if added := schema.get("x-version-added"):
            lines.extend([f".. versionadded:: {added}", ""])
        lines.extend(
            [
                ".. list-table:: Parameters",
                "   :header-rows: 1",
                "",
                "   * - Name",
                "     - Required",
                "     - Type or allowed values",
            ]
        )
        self.parameters(lines, schema)
        self.add_section(name, lines)

    def parameters(
        self, lines: list[str], schema: dict[str, Any], prefix: str = ""
    ) -> None:
        for name, parameter in schema["properties"].items():
            lines.extend(
                [
                    f"   * - ``{prefix}{name}``",
                    f"     - {'Yes' if name in schema.get('required', []) else 'No'}",
                    f"     - {describe_parameter(parameter)}",
                ]
            )
            if "properties" in parameter:
                self.parameters(lines, parameter, f"{prefix}{name}.")
            elif "properties" in parameter.get("items", {}):
                self.parameters(lines, parameter["items"], f"{prefix}{name}[].")

    def handle(
        self, *args: object, output: Path | None = None, **options: object
    ) -> None:
        self.sections.clear()
        self.document("workflows", SCHEMA["title"], SCHEMA, level="-")
        for group, discriminator, variants in (
            ("triggers", "trigger", SCHEMA["properties"]["triggers"]["items"]["oneOf"]),
            ("conditions", "condition", SCHEMA["$defs"]["condition"]["oneOf"]),
            ("actions", "action", SCHEMA["$defs"]["action"]["oneOf"]),
        ):
            self.add_section(group, [group.capitalize(), "-" * len(group), ""])
            for variant in variants:
                selector = variant["properties"].get(discriminator)
                if selector is None:
                    names = [next(iter(variant["properties"]))]
                else:
                    names = selector.get("enum", [selector.get("const")])
                for name in names:
                    schema = variant
                    if selector is not None:
                        schema = variant | {
                            "properties": variant["properties"]
                            | {discriminator: {"const": name}}
                        }
                    self.document(
                        f"{discriminator}-{name}", schema.get("title", name), schema
                    )
        self.add_section(
            "cookbook", [".. _automation-cookbook:", "", "Cookbook", "--------"]
        )
        self.write_sections(output)
