# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Private registry of built-in automation operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import F
from jsonschema import Draft202012Validator

from weblate.addons.ai import (
    AIEvaluationAddon,
    available_evaluation_services,
    effective_evaluator,
    evaluate_component,
)
from weblate.machinery.llm import BaseLLMTranslation
from weblate.machinery.models import MACHINERY
from weblate.trans.automation import UnitSelection, automatic_translation, bulk_edit
from weblate.trans.forms import AutoForm, BulkEditForm
from weblate.trans.models import Component
from weblate.utils.forms import QueryField

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
    supported_scopes: ClassVar[frozenset[str]] = frozenset({"component"})
    query_required_for_component: ClassVar[bool] = False

    @classmethod
    def normalize(
        cls,
        settings: dict[str, Any],
        obj: Component | Project | None,
        *,
        scope: str = "component",
    ) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def execute(
        cls,
        component: Component,
        settings: dict[str, Any],
        user: User | None,
        *,
        selection: UnitSelection | None = None,
        affected: UnitSelection | None = None,
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
    action: dict[str, Any],
    component: Component,
    user: User | None,
    selection: UnitSelection | None = None,
    affected: UnitSelection | None = None,
) -> dict[str, Any]:
    from django.utils.translation import override  # ruff: ignore[import-outside-top-level]

    operation = get_operation(action["action"])
    # Persisted results must not depend on the worker's active UI language.
    with override("en"):
        result = operation.execute(
            component,
            action["settings"],
            user,
            selection=selection,
            affected=affected,
        )
        validate_result(operation, result)
        return result


@register
class AutomaticTranslationOperation(AutomationOperation):
    name = "weblate.automatic_translation"
    title = "Automatic translation"
    version_added = "2026.10"
    supported_scopes = frozenset({"component", "trigger", "result"})
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
        cls,
        settings: dict[str, Any],
        obj: Component | Project | None,
        *,
        scope: str = "component",
    ) -> dict[str, Any]:
        data = {
            "mode": "suggest",
            "q": "state:<translated" if scope == "component" else "",
            "auto_source": "others",
            "component": None,
            "engines": [],
            "threshold": 80,
        } | settings
        form = AutoForm(obj=obj, user=None, data=data)
        if scope != "component":
            form.fields["q"].required = False
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
        cls,
        component: Component,
        settings: dict[str, Any],
        user: User | None,
        *,
        selection: UnitSelection | None = None,
        affected: UnitSelection | None = None,
    ) -> dict[str, Any]:
        result = automatic_translation(
            component,
            settings,
            user,
            enforce_permissions=False,
            selection=selection,
            affected=affected,
        )
        warnings = result["warnings"]
        result["warnings"] = [str(warning)[:1024] for warning in warnings[:20]]
        result["warnings_omitted"] = max(0, len(warnings) - 20)
        return result


@register
class AIQualityOperation(AutomationOperation):
    name = "weblate.ai_quality"
    title = "AI quality evaluation"
    version_added = "2026.10"
    supported_scopes = frozenset({"component", "trigger", "result"})
    settings_schema = object_schema({"service": STRING, "q": STRING}, ["service"])
    result_schema = object_schema(
        {
            "component": {"type": "integer"},
            "evaluated": {"type": "integer", "minimum": 0},
        },
        ["component", "evaluated"],
    )

    @classmethod
    def normalize(
        cls,
        settings: dict[str, Any],
        obj: Component | Project | None,
        *,
        scope: str = "component",  # ruff: ignore[unused-class-method-argument]
    ) -> dict[str, Any]:
        service = settings["service"]
        project = obj.project if isinstance(obj, Component) else obj
        configured = project.get_machinery_settings() if project else None
        available = (
            available_evaluation_services(configured)
            if configured is not None
            else [
                key
                for key, machine in MACHINERY.items()
                if issubclass(machine, BaseLLMTranslation)
            ]
        )
        if service not in available:
            msg = "The configured evaluation service is unavailable."
            raise ValidationError(msg)
        query = QueryField().clean(settings.get("q", ""))
        if isinstance(obj, Component):
            evaluator = effective_evaluator(obj)
            if (
                evaluator is None
                or evaluator.addon.get_configuration()["service"] != service
            ):
                msg = "AI quality evaluation requires a matching add-on."
                raise ValidationError(msg)
        return {"service": service, "q": query}

    @classmethod
    def execute(
        cls,
        component: Component,
        settings: dict[str, Any],
        _user: User | None,
        *,
        selection: UnitSelection | None = None,
        affected: UnitSelection | None = None,
    ) -> dict[str, Any]:
        evaluator = effective_evaluator(component)
        if (
            evaluator is None
            or evaluator.addon.get_configuration()["service"] != settings["service"]
        ):
            msg = "AI quality evaluation requires a matching add-on."
            raise ValueError(msg)
        configuration = evaluator.addon.get_configuration()
        units = (
            (selection or UnitSelection())
            .queryset(component)
            .exclude(pk=F("source_unit_id"))
        )
        if settings["q"]:
            units = units.search(settings["q"], project=component.project)
        evaluated: set[int] = set()
        result = evaluate_component(
            AIEvaluationAddon(evaluator),
            component,
            configuration,
            units.values_list("pk", flat=True),
            scheduled=False,
            evaluated_unit_ids=evaluated,
        )
        component.drop_addons_cache()
        current = effective_evaluator(component)
        if (
            current is None
            or current.pk != evaluator.pk
            or current.addon.get_configuration() != configuration
        ):
            msg = "AI quality evaluation add-on changed during execution."
            raise ValueError(msg)
        if result["failed"] or result["skipped"]:
            msg = "AI quality evaluation was incomplete."
            raise ValueError(msg)
        if affected is not None:
            affected.unit_ids = evaluated
        return {"component": component.pk, "evaluated": result["evaluated"]}


@register
class BulkEditOperation(AutomationOperation):
    name = "weblate.bulk_edit"
    title = "Bulk editing"
    version_added = "2026.10"
    supported_scopes = frozenset({"component", "trigger", "result"})
    query_required_for_component = True
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
        [],
    )
    result_schema = object_schema(
        {"component": {"type": "integer"}, "updated": {"type": "integer"}},
        ["component", "updated"],
    )

    @classmethod
    def normalize(
        cls,
        settings: dict[str, Any],
        obj: Component | Project | None,
        *,
        scope: str = "component",
    ) -> dict[str, Any]:
        if scope != "component":
            settings.setdefault("q", "")
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
        if scope != "component":
            form.fields["q"].required = False
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
        cls,
        component: Component,
        settings: dict[str, Any],
        _user: User | None,
        *,
        selection: UnitSelection | None = None,
        affected: UnitSelection | None = None,
    ) -> dict[str, Any]:
        return bulk_edit(component, settings, selection, affected)
