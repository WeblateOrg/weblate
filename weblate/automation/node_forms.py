# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Forms rendering individual workflow nodes in the visual automation editor."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy

from weblate.automation.schema import CANONICAL_CHANGE_ACTIONS
from weblate.trans.actions import ActionEvents
from weblate.utils.forms import QueryField
from weblate.utils.state import StringState


def change_event_choices() -> list[tuple[str, str]]:
    """Offer documented change-event identifiers with their localized labels."""
    labels = {action.value: action.label for action in ActionEvents}
    return sorted(
        (
            (identifier, str(labels[value]))
            for identifier, value in CANONICAL_CHANGE_ACTIONS.items()
        ),
        key=lambda choice: choice[1].casefold(),
    )


class ChangeTriggerForm(forms.Form):
    events = forms.MultipleChoiceField(
        label=gettext_lazy("Change events"),
        choices=[],
        help_text=gettext_lazy("The workflow runs for each of the selected events."),
    )

    def __init__(self) -> None:
        super().__init__()
        self.fields["events"].choices = change_event_choices()


class ExpressionConditionForm(forms.Form):
    value = forms.CharField(
        label=gettext_lazy("CEL expression"),
        widget=forms.Textarea(attrs={"rows": 2, "class": "font-monospace"}),
        help_text=gettext_lazy("The expression has to evaluate to a boolean."),
    )


class ComponentCategoryConditionForm(forms.Form):
    value = forms.CharField(
        label=gettext_lazy("Category path"),
        help_text=gettext_lazy("Slash-separated category path inside the project."),
    )


class LanguageConditionForm(forms.Form):
    value = forms.CharField(
        label=gettext_lazy("Language code"),
    )


class MatchingStringsConditionForm(forms.Form):
    value = QueryField(required=True)


class ChangeActionConditionForm(forms.Form):
    value = forms.ChoiceField(label=gettext_lazy("Change event"), choices=[])

    def __init__(self) -> None:
        super().__init__()
        self.fields["value"].choices = change_event_choices()


class UnitStateConditionForm(forms.Form):
    value = forms.ChoiceField(
        label=gettext_lazy("String state"),
        choices=StringState.choices,
    )


def action_chrome_form(supported_scopes: frozenset[str]) -> forms.Form:
    """Build the fields shared by every action node."""
    form = forms.Form()
    form.fields["id"] = forms.RegexField(
        label=gettext_lazy("Action ID"),
        regex="^[a-z][a-z0-9_]{0,63}$",
        required=False,
        help_text=gettext_lazy(
            "Optional identifier so that later actions can use its results."
        ),
    )
    scopes = [
        ("component", gettext_lazy("Whole component")),
        ("trigger", gettext_lazy("String affected by the change")),
    ]
    form.fields["scope"] = forms.ChoiceField(
        label=gettext_lazy("String scope"),
        required=False,
        choices=[
            ("", gettext_lazy("Default (whole component)")),
            *(choice for choice in scopes if choice[0] in supported_scopes),
        ],
    )
    return form


TRIGGER_FORMS: dict[str, type[forms.Form]] = {"change": ChangeTriggerForm}

CONDITION_FORMS: dict[str, type[forms.Form]] = {
    "expression": ExpressionConditionForm,
    "component_category": ComponentCategoryConditionForm,
    "language": LanguageConditionForm,
    "matching_strings": MatchingStringsConditionForm,
    "change_action": ChangeActionConditionForm,
    "unit_state": UnitStateConditionForm,
}
