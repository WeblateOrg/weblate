#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


class TermForm(forms.ModelForm):
    """Form for adding term to a glossary."""

    terms = CommaSeparatedIntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Unit
        fields = ["source", "target", "translation"]
        widgets = {
            "source": forms.TextInput,
            "target": forms.TextInput,
        }
        field_classes = {
            "translation": GlossaryModelChoiceField,
        }

    def __init__(self, unit, data=None, instance=None, initial=None, **kwargs):
        glossaries = Translation.objects.filter(
            language=unit.translation.language,
            component__in=unit.translation.component.project.glossaries,
        )
        if not instance and not initial:
            initial = {}
        if initial is not None and "glossary" not in initial and len(glossaries) == 1:
            initial["translation"] = glossaries[0]
        super().__init__(data=data, instance=instance, initial=initial, **kwargs)
        self.fields["translation"].queryset = glossaries
        self.fields["translation"].label = _("Glossary")
