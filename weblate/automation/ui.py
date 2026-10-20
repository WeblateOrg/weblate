# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Metadata and node forms backing the visual automation editor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django.utils.translation import gettext_lazy

from weblate.automation.node_forms import (
    CONDITION_FORMS,
    TRIGGER_FORMS,
    action_chrome_form,
)
from weblate.automation.operations import OPERATIONS
from weblate.automation.schema import SCHEMA

if TYPE_CHECKING:
    from django import forms
    from django_stubs_ext import StrOrPromise

    from weblate.trans.models import Component, Project

TRIGGER_TITLES: dict[str, StrOrPromise] = {
    "change": gettext_lazy("Change event"),
    "daily": gettext_lazy("Daily"),
    "component_update": gettext_lazy("Component update"),
    "post_update": gettext_lazy("Repository update"),
    "post_commit": gettext_lazy("Repository commit"),
    "post_push": gettext_lazy("Repository push"),
    "manual": gettext_lazy("Manual run"),
}

CONDITION_TITLES: dict[str, StrOrPromise] = {
    "expression": gettext_lazy("Expression"),
    "component_category": gettext_lazy("Component category"),
    "language": gettext_lazy("Language"),
    "matching_strings": gettext_lazy("Matching strings"),
    "change_action": gettext_lazy("Change event"),
    "unit_state": gettext_lazy("String state"),
    "and": gettext_lazy("All of"),
    "or": gettext_lazy("Any of"),
    "not": gettext_lazy("Not"),
}

# Node kinds whose editing support is still to come; workflows using them are
# edited as YAML.
NESTING_CONDITIONS = frozenset({"and", "or", "not"})
NESTING_ACTIONS = frozenset({"sequence", "choose"})


@dataclass
class EditorNode:
    kind: str
    name: str
    title: StrOrPromise
    emit: dict[str, Any]
    form: forms.Form | None = None
    chrome: forms.Form | None = None
    group: str | None = None

    @property
    def emit_json(self) -> str:
        return json.dumps(self.emit, sort_keys=True)


@dataclass
class EditorContext:
    triggers: list[EditorNode] = field(default_factory=list)
    conditions: list[EditorNode] = field(default_factory=list)
    actions: list[EditorNode] = field(default_factory=list)


def workflow_type(schema: dict[str, Any]) -> str:
    """Map a JSON Schema fragment onto the editor's serialization types."""
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), None)
    if kind is None and "enum" in schema:
        kind = (
            "integer"
            if all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in schema["enum"]
            )
            else "string"
        )
    if kind == "array":
        return "list"
    if kind == "integer":
        return "integer"
    return "string"


def prepare_node_form(
    form: forms.Form,
    properties: dict[str, Any],
    required: set[str],
    prefix: str,
) -> forms.Form:
    """
    Restrict a form to the keys of a node and annotate it for the editor.
    """
    names = [name for name in properties if name in form.fields]
    for name in list(form.fields):
        if name not in names:
            del form.fields[name]
    for name in names:
        schema = properties[name]
        widget = form.fields[name].widget
        widget.attrs["data-workflow-key"] = name
        widget.attrs["data-workflow-type"] = workflow_type(schema)
        if name in required:
            widget.attrs["data-workflow-required"] = "1"
    form.auto_id = f"id_{prefix}_%s"
    helper = FormHelper(form)
    helper.form_tag = False
    helper.disable_csrf = True
    helper.layout = Layout(*[Field(name) for name in names])
    cast("Any", form).helper = helper
    return form


def schema_variants(group: str, discriminator: str) -> list[tuple[str, dict[str, Any]]]:
    """
    Enumerate the schema variants of a node group by their discriminator.
    """
    if group == "triggers":
        variants = SCHEMA["properties"]["triggers"]["items"]["oneOf"]
    else:
        variants = SCHEMA["$defs"][discriminator]["oneOf"]
    result: list[tuple[str, dict[str, Any]]] = []
    for variant in variants:
        selector = variant["properties"].get(discriminator)
        if selector is None:
            # Structural actions such as sequence and choose have no
            # discriminator; they are named after their only required key.
            names = [next(iter(variant["properties"]))]
        else:
            names = selector.get("enum", [selector.get("const")])
        result.extend((name, variant) for name in names)
    return result


def trigger_nodes() -> list[EditorNode]:
    nodes = []
    for name, variant in schema_variants("triggers", "trigger"):
        form_class = TRIGGER_FORMS.get(name)
        nodes.append(
            EditorNode(
                kind=f"trigger:{name}",
                name=name,
                title=TRIGGER_TITLES[name],
                emit={"trigger": name},
                form=prepare_node_form(
                    form_class(),
                    {
                        key: schema
                        for key, schema in variant["properties"].items()
                        if key != "trigger"
                    },
                    set(variant.get("required", [])),
                    f"automation_trigger_{name}",
                )
                if form_class is not None
                else None,
            )
        )
    return sorted(nodes, key=lambda node: str(node.title).casefold())


def condition_nodes() -> list[EditorNode]:
    nodes = []
    for name, variant in schema_variants("conditions", "condition"):
        if name in NESTING_CONDITIONS:
            continue
        nodes.append(
            EditorNode(
                kind=f"condition:{name}",
                name=name,
                title=CONDITION_TITLES[name],
                emit={"condition": name},
                form=prepare_node_form(
                    CONDITION_FORMS[name](),
                    {
                        key: schema
                        for key, schema in variant["properties"].items()
                        if key != "condition"
                    },
                    set(variant.get("required", [])),
                    f"automation_condition_{name}",
                ),
            )
        )
    return sorted(nodes, key=lambda node: str(node.title).casefold())


def action_nodes(obj: Component | Project | None) -> list[EditorNode]:
    nodes = []
    for name, variant in schema_variants("actions", "action"):
        if name in NESTING_ACTIONS:
            continue
        operation = OPERATIONS[name]
        settings_schema = operation.settings_schema
        required = set(settings_schema.get("required", []))
        if operation.query_required_for_component:
            required.add("q")
        slug = name.replace(".", "_")
        nodes.append(
            EditorNode(
                kind=f"action:{name}",
                name=name,
                title=operation.verbose,
                emit={"action": name, "settings": {}},
                form=prepare_node_form(
                    operation.settings_form(obj),
                    settings_schema["properties"],
                    required,
                    f"automation_settings_{slug}",
                ),
                chrome=prepare_node_form(
                    action_chrome_form(operation.supported_scopes),
                    {
                        key: schema
                        for key, schema in variant["properties"].items()
                        if key in {"id", "scope"}
                    },
                    set(),
                    f"automation_action_{slug}",
                ),
                group="settings",
            )
        )
    return sorted(nodes, key=lambda node: str(node.title).casefold())


def editor_context(obj: Component | Project | None) -> dict[str, Any]:
    """Build the template context of the visual editor."""
    return {
        "editor": EditorContext(
            triggers=trigger_nodes(),
            conditions=condition_nodes(),
            actions=action_nodes(obj),
        )
    }
