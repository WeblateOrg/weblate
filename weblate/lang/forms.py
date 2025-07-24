# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.conf import settings

from weblate.lang.models import Language, Plural
from weblate.utils.forms import ContextDiv


class LanguageForm(forms.ModelForm):
    class Meta:
        model = Language
        fields = ["code", "name", "direction", "population"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            ContextDiv(
                template="lang/language_edit_warning.html",
                context={"update_languages": settings.UPDATE_LANGUAGES},
            ),
            Field("code"),
            Field("name"),
            Field("direction"),
            Field("population"),
        )

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
