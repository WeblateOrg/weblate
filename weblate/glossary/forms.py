#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from weblate.trans.models import Translation, Unit


class CommaSeparatedIntegerField(forms.Field):
    def to_python(self, value):
        if not value:
            return []

        try:
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        except (ValueError, TypeError):
            raise ValidationError(_("Invalid integer list!"))


class GlossaryModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.component.name


class GlossaryAddMixin(forms.Form):
    terminology = forms.BooleanField(
        label=gettext_lazy("Terminology"),
        help_text=gettext_lazy("String will be part of the glossary in all languages"),
        required=False,
    )
    forbidden = forms.BooleanField(
        label=gettext_lazy("Forbidden translation"),
        required=False,
    )
    read_only = forms.BooleanField(
        label=gettext_lazy("Untranslatable term"),
        required=False,
    )

    def get_glossary_flags(self):
        result = []
        if self.cleaned_data.get("terminology"):
            result.append("terminology")
        if self.cleaned_data.get("forbidden"):
            result.append("forbidden")
        if self.cleaned_data.get("read_only"):
            result.append("read-only")
        return ", ".join(result)


class TermForm(GlossaryAddMixin, forms.ModelForm):
    """Form for adding term to a glossary."""

    terms = CommaSeparatedIntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Unit
        fields = ["source", "target", "translation", "explanation"]
        widgets = {
            "source": forms.TextInput,
            "target": forms.TextInput,
            "explanation": forms.TextInput,
        }
        field_classes = {
            "translation": GlossaryModelChoiceField,
        }

    def __init__(self, unit, user, data=None, instance=None, initial=None, **kwargs):
        translation = unit.translation
        component = translation.component
        glossaries = Translation.objects.filter(
            language=translation.language,
            component__in=component.project.glossaries,
            component__manage_units=True,
        )
        self._user = user
        exclude = [
            glossary.pk
            for glossary in glossaries
            if not user.has_perm("unit.add", glossary)
        ]
        if exclude:
            glossaries = glossaries.exclude(pk__in=exclude)

        if not instance and not initial:
            initial = {}
        if initial is not None and unit.is_source:
            initial["terminology"] = True
        if initial is not None and "glossary" not in initial and len(glossaries) == 1:
            initial["translation"] = glossaries[0]
        super().__init__(data=data, instance=instance, initial=initial, **kwargs)
        self.fields["translation"].queryset = glossaries
        self.fields["translation"].label = _("Glossary")
        self.fields["source"].label = str(component.source_language)
        self.fields["source"].required = True
        self.fields["target"].label = str(translation.language)
        if translation.is_source:
            self.fields["target"].widget = forms.HiddenInput()

    def clean(self):
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
            "context": "",
            "source": self.cleaned_data["source"],
            "target": self.cleaned_data["source"]
            if is_source
            else self.cleaned_data.get("target"),
            "auto_context": True,
            "extra_flags": self.get_glossary_flags(),
            "explanation": self.cleaned_data.get("explanation"),
        }
