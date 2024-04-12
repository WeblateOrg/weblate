# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from weblate.trans.forms import NewBilingualGlossaryUnitForm
from weblate.trans.models import Translation, Unit


class CommaSeparatedIntegerField(forms.Field):
    def to_python(self, value):
        if not value:
            return []

        try:
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        except (ValueError, TypeError):
            raise ValidationError(gettext("Invalid integer list!"))


class GlossaryModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
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

    def __init__(
        self, unit, user, data=None, instance=None, initial=None, **kwargs
    ) -> None:
        translation = unit.translation
        component = translation.component
        glossaries = Translation.objects.filter(
            language=translation.language,
            component__in=component.project.glossaries,
            component__manage_units=True,
        )
        exclude = [
            glossary.pk
            for glossary in glossaries
            if not user.has_perm("glossary.add", glossary)
        ]
        if exclude:
            glossaries = glossaries.exclude(pk__in=exclude)

        if not instance and not initial:
            initial = {}
        if initial is not None and unit.is_source:
            initial["terminology"] = True
        if initial is not None and "glossary" not in initial and len(glossaries) == 1:
            initial["translation"] = glossaries[0]
        kwargs["auto_id"] = "id_add_term_%s"
        super().__init__(
            translation=translation,
            user=user,
            data=data,
            instance=instance,
            initial=initial,
            **kwargs,
        )
        self.fields["translation"].queryset = glossaries
        self.fields["translation"].label = gettext("Glossary")
        if translation.is_source:
            self.fields["target"].required = False
            self.fields["target"].widget = forms.HiddenInput()

    def clean(self) -> None:
        translation = self.cleaned_data.get("translation")
        if not translation:
            return
        try:
            data = self.as_kwargs()
        except KeyError:
            # Probably some fields validation has failed
            return
        translation.validate_new_unit_data(**data)

    def as_kwargs(self):
        is_source = self.cleaned_data["translation"].is_source
        return {
            "context": self.cleaned_data.get("context", ""),
            "source": self.cleaned_data["source"],
            "target": self.cleaned_data["source"]
            if is_source
            else self.cleaned_data.get("target"),
            "auto_context": bool(self.cleaned_data.get("auto_context", False)),
            "extra_flags": self.get_glossary_flags(),
            "explanation": self.cleaned_data.get("explanation"),
            "skip_existing": bool(self.cleaned_data.get("terminology")),
        }
