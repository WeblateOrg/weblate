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
from crispy_forms.helper import FormHelper
from django import forms

from weblate.lang.models import Language, Plural


class LanguageForm(forms.ModelForm):
    class Meta:
        model = Language
        exclude = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

    @staticmethod
    def get_field_doc(field):
        return ("admin/languages", f"language-{field.name}")


class PluralForm(forms.ModelForm):
    class Meta:
        model = Plural
        fields = ["number", "formula"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

    @staticmethod
    def get_field_doc(field):
        return ("admin/languages", f"plural-{field.name}")
