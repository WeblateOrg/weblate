# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Fieldset, Layout
from django import forms
from django.utils.translation import gettext

from weblate.trans.forms import FieldDocsMixin, setup_message_setting_site_defaults
from weblate.utils.forms import SearchableSelect, SortedSelect
from weblate.workspaces.models import Workspace


class WorkspaceSettingsForm(FieldDocsMixin, forms.ModelForm):
    class Meta:
        model = Workspace
        fields = (
            "name",
            "license",
            "agreement",
            "new_lang",
            "language_code_style",
            "secondary_language",
            "check_flags",
            "commit_message",
            "add_message",
            "delete_message",
            "merge_message",
            "addon_message",
            "pull_message",
        )
        # ruff: ignore[mutable-class-default]
        widgets = {
            "license": SearchableSelect,
            "language_code_style": SortedSelect,
            "secondary_language": SortedSelect,
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        setup_message_setting_site_defaults(self.fields)
        self._missing_fields: set[str] = set()
        if self.is_bound and self.instance.pk:
            for field_name, field in self.fields.items():
                if field_name not in self.data:
                    self._missing_fields.add(field_name)
                    field.required = False
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            "name",
            Fieldset(
                gettext("Inherited component defaults"),
                "license",
                "agreement",
                "new_lang",
                "language_code_style",
                "secondary_language",
                "check_flags",
            ),
            Fieldset(
                gettext("Commit messages"),
                "commit_message",
                "add_message",
                "delete_message",
                "merge_message",
                "addon_message",
                "pull_message",
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data is None:
            return cleaned_data
        for field_name in self._missing_fields:
            cleaned_data[field_name] = getattr(self.instance, field_name)
        return cleaned_data

    def get_field_doc(self, field: forms.Field) -> tuple[str, str] | None:
        field_name = getattr(field, "name", "")
        return ("admin/workspaces", f"workspace-{field_name.replace('_', '-')}")
