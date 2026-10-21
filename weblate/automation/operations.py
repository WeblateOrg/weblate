# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Private registry of built-in automation operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import F
from django.utils.translation import gettext_lazy
from jsonschema import Draft202012Validator

from weblate.addons.ai import (
    AIEvaluationAddon,
    EvaluatedUnitSnapshot,
    available_evaluation_services,
    effective_evaluator,
    evaluate_component,
)
from weblate.machinery.models import (
    MACHINERY,
    machinery_settings_for_project,
    resolve_installation,
)
from weblate.trans.automation import UnitSelection, automatic_translation, bulk_edit
from weblate.trans.forms import AutoForm, BulkEditForm
from weblate.trans.models import Component, Project
from weblate.utils.forms import QueryField

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import User


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
    verbose: ClassVar[StrOrPromise]
    version_added: ClassVar[str]
    settings_schema: ClassVar[dict[str, Any]]
    result_schema: ClassVar[dict[str, Any]]
    supported_scopes: ClassVar[frozenset[str]] = frozenset({"component"})
    query_required_for_component: ClassVar[bool] = False
    preview_safe: ClassVar[bool] = False

    @classmethod
    def settings_form(cls, obj: Component | Project | None) -> forms.Form:
        """Return an unbound form rendering this operation's settings."""
        raise NotImplementedError

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


def build_settings_form(**fields: forms.Field) -> forms.Form:
    """Build an unbound form out of explicit fields for the visual editor."""
    form = forms.Form()
    form.fields.update(fields)
    return form


def evaluation_service_choices(
    obj: Component | Project | None,
) -> list[tuple[str, str]]:
    """List evaluation services offered by the AI quality add-on for this scope."""
    project = obj.project if isinstance(obj, Component) else obj
    configured = (
        project.get_machinery_settings()
        if project is not None
        else machinery_settings_for_project()
    )
    choices = []
    for key in available_evaluation_services(configured):
        engine = MACHINERY[key.partition(":")[0]]
        choices.append((key, f"{engine.name} ({key})"))
        if slug := configured.get(key, {}).get("_installation_slug"):
            alias = f"{key.partition(':')[0]}:{slug}"
            choices.append((alias, f"{engine.name} ({alias})"))
    return choices


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
class SelectOperation(AutomationOperation):
    name = "weblate.select"
    title = "Select strings"
    verbose = gettext_lazy("Select strings")
    version_added = "2026.11"
    supported_scopes = frozenset({"component", "trigger", "result"})
    query_required_for_component = True
    preview_safe = True
    settings_schema = object_schema({"q": STRING}, [])
    result_schema = object_schema(
        {
            "component": {"type": "integer"},
            "selected": {"type": "integer", "minimum": 0},
        },
        ["component", "selected"],
    )

    @classmethod
    def settings_form(
        cls,
        obj: Component | Project | None,  # ruff: ignore[unused-class-method-argument]
    ) -> forms.Form:
        return build_settings_form(q=QueryField(required=True))

    @classmethod
    def normalize(
        cls,
        settings: dict[str, Any],
        obj: Component | Project | None,  # ruff: ignore[unused-class-method-argument]
        *,
        scope: str = "component",
    ) -> dict[str, Any]:
        return {
            "q": QueryField(required=scope == "component").clean(
                settings.get("q", "").strip()
            )
        }

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
        if selection is None:
            selection = UnitSelection()
        query = settings["q"]
        if query:
            units = selection.queryset(component).search(
                query, project=component.project
            )
            if affected is None:
                selected = units.count()
            else:
                selected_ids: set[int] = set()
                source_ids: set[int] = set()
                for unit_id, source_id in units.values_list(
                    "pk", "source_unit_id"
                ).iterator(chunk_size=2000):
                    selected_ids.add(unit_id)
                    if source_id is not None:
                        source_ids.add(source_id)
                selected = len(selected_ids)
                affected.unit_ids = selected_ids
                affected.source_unit_ids = source_ids
                if selection.unit_snapshots is not None:
                    affected.unit_snapshots = {
                        unit_id: snapshot
                        for unit_id, snapshot in selection.unit_snapshots.items()
                        if unit_id in selected_ids
                    }
        else:
            selected = selection.count(component)
            if affected is not None:
                affected.unit_ids = (
                    selection.unit_ids.copy()
                    if selection.unit_ids is not None
                    else None
                )
                affected.source_unit_ids = selection.source_unit_ids.copy()
                affected.expand_source_ids = selection.expand_source_ids.copy()
                affected.unit_snapshots = (
                    selection.unit_snapshots.copy()
                    if selection.unit_snapshots is not None
                    else None
                )
        return {"component": component.pk, "selected": selected}


@register
class AutomaticTranslationOperation(AutomationOperation):
    name = "weblate.automatic_translation"
    title = "Automatic translation"
    verbose = gettext_lazy("Automatic translation")
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
    def auto_form(
        cls, obj: Component | Project | None, data: dict[str, Any] | None = None
    ) -> AutoForm:
        form = AutoForm(obj=obj, user=None, data=data)
        cast("forms.ChoiceField", form.fields["mode"]).choices = cast(
            "forms.ChoiceField", AutoForm.base_fields["mode"]
        ).choices
        return form

    @classmethod
    def settings_form(cls, obj: Component | Project | None) -> forms.Form:
        form = cls.auto_form(obj)
        if not isinstance(form.fields["component"], forms.ChoiceField):
            form.fields["component"] = forms.IntegerField(
                label=gettext_lazy("Component"),
                required=False,
                min_value=1,
                help_text=AutoForm.COMPONENT_ID_HELP_TEXT,
            )
        return form

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
        form = cls.auto_form(obj, data)
        if scope != "component":
            form.fields["q"].required = False
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
            # The saved workflow, rather than the triggering actor, authorizes
            # the operation and its documented cross-component sources.
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
    verbose = gettext_lazy("AI quality evaluation")
    version_added = "2026.10"
    supported_scopes = frozenset({"component", "trigger", "result"})
    settings_schema = object_schema({"service": STRING, "q": STRING}, [])
    result_schema = object_schema(
        {
            "component": {"type": "integer"},
            "evaluated": {"type": "integer", "minimum": 0},
        },
        ["component", "evaluated"],
    )

    @classmethod
    def settings_form(cls, obj: Component | Project | None) -> forms.Form:
        return build_settings_form(
            service=forms.ChoiceField(
                label=gettext_lazy("Evaluation service"),
                required=False,
                choices=[
                    ("", gettext_lazy("Use the effective AI quality add-on")),
                    *evaluation_service_choices(obj),
                ],
            ),
            q=QueryField(),
        )

    @staticmethod
    def services_match(first: str, second: str, project: Project) -> bool:
        """Compare current installations while preserving saved selector aliases."""
        try:
            return (
                resolve_installation(first, project).pk
                == resolve_installation(second, project).pk
            )
        except ValueError:
            return False

    @classmethod
    def normalize(
        cls,
        settings: dict[str, Any],
        obj: Component | Project | None,
        *,
        scope: str = "component",  # ruff: ignore[unused-class-method-argument]
    ) -> dict[str, Any]:
        query = QueryField().clean(settings.get("q", ""))
        service = settings.get("service")
        if isinstance(obj, Component):
            evaluator = effective_evaluator(obj)
            if evaluator is None:
                msg = "AI quality evaluation requires an effective add-on."
                raise ValidationError(msg)
            if service is not None and not cls.services_match(
                service,
                evaluator.addon.get_configuration()["service"],
                obj.project,
            ):
                msg = (
                    "AI quality evaluation service does not match the effective add-on."
                )
                raise ValidationError(msg)
        if service is not None:
            project = obj.project if isinstance(obj, Component) else obj
            configured = (
                project.get_machinery_settings()
                if project
                else machinery_settings_for_project()
            )
            try:
                installation = resolve_installation(service, project)
            except ValueError as error:
                raise ValidationError(str(error)) from error
            if installation.selector not in available_evaluation_services(configured):
                msg = "The configured evaluation service is unavailable."
                raise ValidationError(msg)
        return {"q": query, **({"service": service} if service is not None else {})}

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
        if evaluator is None:
            msg = "AI quality evaluation requires an effective add-on."
            raise ValueError(msg)
        configuration = evaluator.addon.get_configuration()
        if "service" in settings and not cls.services_match(
            settings["service"], configuration["service"], component.project
        ):
            msg = "AI quality evaluation service does not match the effective add-on."
            raise ValueError(msg)
        units = (
            (selection or UnitSelection())
            .queryset(component)
            .exclude(pk=F("source_unit_id"))
        )
        if settings["q"]:
            units = units.search(settings["q"], project=component.project)
        evaluated: set[int] = set()
        snapshots: dict[int, EvaluatedUnitSnapshot] = {}
        result = evaluate_component(
            AIEvaluationAddon(evaluator),
            component,
            configuration,
            units.values_list("pk", flat=True),
            scheduled=False,
            evaluated_unit_ids=evaluated,
            evaluated_unit_snapshots=snapshots,
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
            affected.unit_snapshots = snapshots
        return {"component": component.pk, "evaluated": result["evaluated"]}


@register
class BulkEditOperation(AutomationOperation):
    name = "weblate.bulk_edit"
    title = "Bulk editing"
    verbose = gettext_lazy("Bulk editing")
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
    def settings_form(cls, obj: Component | Project | None) -> forms.Form:
        project = obj.project if isinstance(obj, Component) else obj
        form = BulkEditForm(obj=obj, project=project, user=None)
        for name in ("add_labels", "remove_labels"):
            field = cast("forms.ModelMultipleChoiceField", form.fields[name])
            field.to_field_name = "name"
            field.widget = forms.SelectMultiple()
            field.widget.choices = field.choices
        return form

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
        user: User | None,
        *,
        selection: UnitSelection | None = None,
        affected: UnitSelection | None = None,
    ) -> dict[str, Any]:
        return bulk_edit(component, settings, user, selection, affected)
