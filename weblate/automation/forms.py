# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Any, cast

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy
from ruamel.yaml import YAML

from weblate.addons.forms import BaseAddonForm
from weblate.automation.definition import (
    normalize_change_events,
    parse_workflow,
    validate_workflow_size,
    walk,
)
from weblate.automation.operations import get_operation
from weblate.utils.forms import QueryField

if TYPE_CHECKING:
    from collections.abc import Mapping, MutableMapping

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
    widget = forms.Textarea(attrs={"class": "font-monospace", "spellcheck": "false"})

    def prepare_value(self, value: object) -> object:
        if isinstance(value, dict):
            workflow = cast("dict[str, Any]", normalize_change_events(value))
            ordered: dict[str, Any] = {
                key: workflow[key]
                for key in ("version", "triggers", "conditions", "actions")
                if key in workflow
            }
            ordered.update(
                {key: item for key, item in workflow.items() if key not in ordered}
            )
            yaml = YAML()
            yaml.default_flow_style = False
            yaml.indent(mapping=2, sequence=4, offset=2)
            output = StringIO()
            yaml.dump(ordered, output)
            return output.getvalue()
        return value

    def to_python(self, value: object) -> dict[str, Any]:
        return parse_workflow(value)


class AutomationForm(BaseAddonForm):
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

    def serialize_form(self) -> dict[str, Any]:
        return {"workflow": self.cleaned_data["workflow"]}

    def clean_workflow(self) -> dict[str, Any]:
        instance = self._addon.instance
        obj = instance.component or instance.project
        if instance.category_id:
            obj = instance.category.project
        return validate_operations(self.cleaned_data["workflow"], obj)


class AutomationExecutionForm(forms.Form):
    component = forms.IntegerField(
        label=gettext_lazy("Component ID"),
        min_value=1,
        required=False,
        help_text=gettext_lazy("Required for inherited automations."),
    )
    change = forms.IntegerField(
        label=gettext_lazy("Change ID"),
        min_value=1,
        required=False,
        help_text=gettext_lazy("Required for workflows using only change triggers."),
    )
    preview = forms.BooleanField(
        label=gettext_lazy("Preview without changes"),
        initial=True,
        required=False,
    )

    def __init__(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        initial: MutableMapping[str, Any] | None = None,
        prefix: str | None = None,
    ) -> None:
        super().__init__(data=data, initial=initial, prefix=prefix)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
