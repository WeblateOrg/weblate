# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy

from weblate.addons.forms import BaseAddonForm
from weblate.automation.definition import (
    parse_workflow,
    validate_workflow_size,
    walk,
)
from weblate.automation.operations import get_operation
from weblate.utils.forms import QueryField

if TYPE_CHECKING:
    from weblate.addons.models import Addon
    from weblate.auth.models import User
    from weblate.automation.addon import AutomationAddon
    from weblate.trans.models import Component, Project


def validate_operations(
    workflow: dict[str, Any], obj: Component | Project | None
) -> dict[str, Any]:
    """Reuse Weblate's operation forms; validate inherited settings again at run time."""
    for path, node in walk(workflow):
        if node.get("condition") == "matching_strings":
            QueryField().clean(node["value"])
        if "action" not in node:
            continue
        try:
            node["settings"] = get_operation(node["action"]).normalize(
                node["settings"].copy(), obj, scope=node.get("scope", "component")
            )
        except ValidationError as error:
            raise ValidationError(
                gettext("%(path)s: %(error)s")
                % {"path": path, "error": error.messages[0]}
            ) from error
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
