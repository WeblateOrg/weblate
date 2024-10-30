# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from weblate.trans.forms import NewBilingualGlossaryUnitForm
from weblate.trans.models import Translation, Unit

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models.translation import NewUnitParams


class CommaSeparatedIntegerField(forms.Field):
    def to_python(self, value) -> list[int]:
        if not value:
            return []

        try:
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        except (ValueError, TypeError) as error:
            raise ValidationError(gettext("Invalid integer list!")) from error


class GlossaryModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj) -> str:
        return obj.component.name


class TermForm(NewBilingualGlossaryUnitForm, forms.ModelForm):
    """Form for adding term to a glossary."""

    terms = CommaSeparatedIntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Unit
        fields = ["context", "source", "target", "translation", "explanation"]
        widgets = {
            "context": forms.TextInput,
            "source": forms.TextInput,
            "target": forms.TextInput,
            "explanation": forms.TextInput,
        }
        field_classes = {
            "translation": GlossaryModelChoiceField,
        }

    def __init__(self, unit: Unit, user: User, data: dict | None = None) -> None:
        self.unit = unit
        translation = unit.translation
        self.glossaries = Translation.objects.filter(
            language=translation.language,
            component__in=translation.component.project.glossaries,
            component__manage_units=True,
        )
        exclude = [
            glossary.pk
            for glossary in self.glossaries
            if not user.has_perm("unit.add", glossary)
        ]
        if exclude:
            self.glossaries = self.glossaries.exclude(pk__in=exclude)

        super().__init__(
            translation=translation,
            user=user,
            data=data,
            auto_id="id_add_term_%s",
        )

    def patch_fields(self) -> None:
        super().patch_fields()
        self.fields["translation"].queryset = self.glossaries
        self.fields["translation"].label = gettext("Glossary")
        if len(self.glossaries) == 1:
            self.fields["translation"].initial = self.glossaries[0]

        if self.unit.is_source:
            self.fields["terminology"].initial = True

        if self.unit.translation.is_source:
            self.fields["target"].required = False
            self.fields["target"].widget = forms.HiddenInput()

    def clean(self) -> None:
        self.translation = self.cleaned_data.get("translation")
        # Validate fields only if translation is valid
        if self.translation:
            super().clean()

    def as_kwargs(self) -> NewUnitParams:
        result = super().as_kwargs()
        if self.cleaned_data["translation"].is_source:
            result["target"] = result["source"]
        result["skip_existing"] = bool(self.cleaned_data.get("terminology"))
        return result
