# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Private registry of built-in automation operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from django import forms
from django.core.exceptions import ValidationError
from jsonschema import Draft202012Validator

from weblate.trans.automation import automatic_translation, bulk_edit
from weblate.trans.forms import AutoForm, BulkEditForm
from weblate.trans.models import Component

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Project


def object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


STRING = {"type": "string", "maxLength": 4096}
STRINGS = {"type": "array", "items": STRING, "maxItems": 100}


class AutomationOperation:
    name: ClassVar[str]
    title: ClassVar[str]
    version_added: ClassVar[str]
    settings_schema: ClassVar[dict[str, Any]]
    result_schema: ClassVar[dict[str, Any]]

    @classmethod
    def normalize(
        cls, settings: dict[str, Any], obj: Component | Project | None
    ) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def execute(
        cls, component: Component, settings: dict[str, Any], user: User | None
    ) -> dict[str, Any]:
        raise NotImplementedError


OPERATIONS: dict[str, type[AutomationOperation]] = {}


def register(operation: type[AutomationOperation]) -> type[AutomationOperation]:
    if operation.name in OPERATIONS:
        msg = f"Duplicate automation operation: {operation.name}"
        raise ValueError(msg)
    OPERATIONS[operation.name] = operation
    return operation


def get_operation(name: str) -> type[AutomationOperation]:
    try:
        return OPERATIONS[name]
    except KeyError as error:
        msg = "Unsupported automation operation"
        raise ValueError(msg) from error


def validate_result(
    operation: type[AutomationOperation], result: dict[str, Any]
) -> None:
    error = next(
        Draft202012Validator(operation.result_schema).iter_errors(result), None
    )
    if error is not None:
        msg = f"Invalid result for {operation.name}: {error.message[:1024]}"
        raise ValueError(msg)


def execute_operation(
    action: dict[str, Any], component: Component, user: User | None
) -> dict[str, Any]:
    from django.utils.translation import override  # ruff: ignore[import-outside-top-level]

    operation = get_operation(action["action"])
    # Persisted results must not depend on the worker's active UI language.
    with override("en"):
        result = operation.execute(component, action["settings"], user)
        validate_result(operation, result)
        return result


@register
class AutomaticTranslationOperation(AutomationOperation):
    name = "weblate.automatic_translation"
    title = "Automatic translation"
    version_added = "2026.10"
    settings_schema = object_schema(
        {
            "mode": {"enum": ["suggest", "translate", "fuzzy", "approved"]},
            "q": STRING,
            "auto_source": {"enum": ["others", "mt"]},
            "component": {"type": ["integer", "null"], "minimum": 1},
            "engines": STRINGS,
            "threshold": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        [],
    )
    result_schema = object_schema(
        {
            "component": {"type": "integer"},
            "updated": {"type": "integer"},
            "message": {"type": "string"},
            "warnings": {
                "type": "array",
                "items": {"type": "string", "maxLength": 1024},
                "maxItems": 20,
            },
            "warnings_omitted": {"type": "integer", "minimum": 0},
        },
        ["component", "updated", "message", "warnings", "warnings_omitted"],
    )

    @classmethod
    def normalize(
        cls, settings: dict[str, Any], obj: Component | Project | None
    ) -> dict[str, Any]:
        data = {
            "mode": "suggest",
            "q": "state:<translated",
            "auto_source": "others",
            "component": None,
            "engines": [],
            "threshold": 80,
        } | settings
        form = AutoForm(obj=obj, user=None, data=data)
        cast("forms.ChoiceField", form.fields["mode"]).choices = cast(
            "forms.ChoiceField", AutoForm.base_fields["mode"]
        ).choices
        if obj is None:
            cast("forms.MultipleChoiceField", form.fields["engines"]).choices = [
                (engine, engine) for engine in data["engines"]
            ]
        if not form.is_valid():
            raise ValidationError(form.errors.as_text())
        return {key: form.cleaned_data[key] for key in data}

    @classmethod
    def execute(
        cls, component: Component, settings: dict[str, Any], user: User | None
    ) -> dict[str, Any]:
        result = automatic_translation(
            component, settings, user, enforce_permissions=False
        )
        warnings = result["warnings"]
        result["warnings"] = [str(warning)[:1024] for warning in warnings[:20]]
        result["warnings_omitted"] = max(0, len(warnings) - 20)
        return result


@register
class BulkEditOperation(AutomationOperation):
    name = "weblate.bulk_edit"
    title = "Bulk editing"
    version_added = "2026.10"
    settings_schema = object_schema(
        {
            "q": STRING,
            "state": {"type": "integer"},
            **dict.fromkeys(
                (
                    "add_flags",
                    "remove_flags",
                    "add_translation_flags",
                    "remove_translation_flags",
                ),
                STRING,
            ),
            "add_labels": STRINGS,
            "remove_labels": STRINGS,
        },
        ["q"],
    )
    result_schema = object_schema(
        {"component": {"type": "integer"}, "updated": {"type": "integer"}},
        ["component", "updated"],
    )

    @classmethod
    def normalize(
        cls, settings: dict[str, Any], obj: Component | Project | None
    ) -> dict[str, Any]:
        data = {
            "state": -1,
            "add_flags": "",
            "remove_flags": "",
            "add_translation_flags": "",
            "remove_translation_flags": "",
            "add_labels": [],
            "remove_labels": [],
        } | settings
        project = obj.project if isinstance(obj, Component) else obj
        form = BulkEditForm(obj=obj, project=project, user=None, data=data)
        for name in ("add_labels", "remove_labels"):
            if project is None:
                form.fields[name] = forms.MultipleChoiceField(
                    required=False,
                    choices=[(label, label) for label in cast("list[str]", data[name])],
                )
            else:
                cast(
                    "forms.ModelMultipleChoiceField", form.fields[name]
                ).to_field_name = "name"
        if not form.is_valid():
            raise ValidationError(form.errors.as_text())
        return data

    @classmethod
    def execute(
        cls, component: Component, settings: dict[str, Any], _user: User | None
    ) -> dict[str, Any]:
        return bulk_edit(component, settings)
