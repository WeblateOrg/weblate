# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from crispy_forms.helper import FormHelper
from django import forms

from weblate.lang.models import Language, Plural


class LanguageForm(forms.ModelForm):
    class Meta:
        model = Language
        fields = ["code", "name", "direction", "population"]

    def __init__(self, *args, **kwargs) -> None:
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

    @staticmethod
    def get_field_doc(field):
        return ("admin/languages", f"plural-{field.name}")
