# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy

from weblate.addons.automation_definition import (
    parse_workflow,
    validate_workflow_size,
    walk,
)
from weblate.addons.forms import BaseAddonForm
from weblate.trans.forms import AutoForm, BulkEditForm
from weblate.trans.models import Component, Project
from weblate.utils.forms import QueryField

if TYPE_CHECKING:
    from weblate.addons.automation import AutomationAddon
    from weblate.addons.models import Addon
    from weblate.auth.models import User


def validate_operations(
    workflow: dict[str, Any], obj: Component | Project | None
) -> dict[str, Any]:
    """Reuse Weblate's operation forms; validate inherited settings again at run time."""
    for path, node in walk(workflow):
        if node.get("condition") == "matching_strings":
            QueryField().clean(node["value"])
        if "action" not in node:
            continue
        form: forms.Form
        data = node["settings"].copy()
        if node["action"] == "weblate.automatic_translation":
            data = {
                "mode": "suggest",
                "q": "state:<translated",
                "auto_source": "others",
                "component": None,
                "engines": [],
                "threshold": 80,
            } | data
            form = AutoForm(obj=obj, user=None, data=data)
            cast("forms.ChoiceField", form.fields["mode"]).choices = cast(
                "forms.ChoiceField", AutoForm.base_fields["mode"]
            ).choices
            if obj is None:
                cast("forms.MultipleChoiceField", form.fields["engines"]).choices = [
                    (engine, engine) for engine in data["engines"]
                ]
        else:
            data = {
                "state": -1,
                "add_flags": "",
                "remove_flags": "",
                "add_translation_flags": "",
                "remove_translation_flags": "",
                "add_labels": [],
                "remove_labels": [],
            } | data
            project = obj.project if isinstance(obj, Component) else obj
            form = BulkEditForm(obj=obj, project=project, user=None, data=data)
            for name in ("add_labels", "remove_labels"):
                if project is None:
                    form.fields[name] = forms.MultipleChoiceField(
                        required=False, choices=[(label, label) for label in data[name]]
                    )
                else:
                    cast(
                        "forms.ModelMultipleChoiceField", form.fields[name]
                    ).to_field_name = "name"
        if not form.is_valid():
            raise ValidationError(
                gettext("%(path)s: %(error)s")
                % {"path": path, "error": str(form.errors.as_text())}
            )
        if node["action"] == "weblate.automatic_translation":
            node["settings"] = {key: form.cleaned_data[key] for key in data}
        else:
            node["settings"] = data
    validate_workflow_size(workflow)
    return workflow


class WorkflowField(forms.Field):
    widget = forms.Textarea

    def prepare_value(self, value: object) -> object:
        if isinstance(value, dict):
            return json.dumps(value, indent=2, ensure_ascii=False)
        return value

    def to_python(self, value: object) -> dict[str, Any]:
        return parse_workflow(value)


class AutomationForm(BaseAddonForm):
    public_configuration_fields = frozenset({"workflow"})
    workflow = WorkflowField(
        label=gettext_lazy("Workflow"),
        help_text=gettext_lazy("Enter an automation definition as YAML or JSON."),
        initial={"version": 1, "triggers": [], "actions": []},
    )

    def __init__(
        self,
        user: User | None,
        addon: AutomationAddon,
        instance: Addon | None = None,
        *args: object,
        **kwargs: object,
    ) -> None:
        super().__init__(user, addon, instance, *args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False

    preview_component = forms.IntegerField(
        label=gettext_lazy("Preview component ID"),
        min_value=1,
        required=False,
        help_text=gettext_lazy(
            "Required for inherited automations. Used only for preview."
        ),
    )
    preview_change = forms.IntegerField(
        label=gettext_lazy("Preview change ID"),
        min_value=1,
        required=False,
        help_text=gettext_lazy("Optional event context. Used only for preview."),
    )

    def serialize_form(self) -> dict[str, Any]:
        return {"workflow": self.cleaned_data["workflow"]}

    def clean_workflow(self) -> dict[str, Any]:
        instance = self._addon.instance
        obj = instance.component or instance.project
        if instance.category_id:
            obj = instance.category.project
        return validate_operations(self.cleaned_data["workflow"], obj)
