# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import forms
from django.utils.translation import gettext_lazy

from weblate.screenshots.models import Screenshot
from weblate.trans.forms import QueryField
from weblate.utils.forms import SortedSelect


class ScreenshotEditForm(forms.ModelForm):
    """Screenshot editing."""

    class Meta:
        model = Screenshot
        fields = ("name", "image", "repository_filename")


class LanguageChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.language


class ScreenshotForm(forms.ModelForm):
    """Screenshot upload."""

    class Meta:
        model = Screenshot
        fields = ("name", "repository_filename", "image", "translation")
        widgets = {
            "translation": SortedSelect,
        }
        field_classes = {
            "translation": LanguageChoiceField,
        }

    def __init__(
        self, component, data=None, files=None, instance=None, initial=None
    ) -> None:
        self.component = component
        super().__init__(data=data, files=files, instance=instance, initial=initial)

        translations = component.translation_set.prefetch_related("language")
        if initial and "translation" in initial:
            translations = translations.filter(
                pk__in=(initial["translation"].pk, component.source_translation.pk)
            )
        self.fields["translation"].queryset = translations
        # This is overridden from initial arg of the form
        self.fields["translation"].initial = component.source_translation
        self.fields["translation"].empty_label = None

        self.fields["paste_button"] = forms.CharField(
            widget=PasteButtonWidget(), required=False, label=""
        )

        self.order_fields(
            ["name", "repository_filename", "paste_button", "image", "translation"]
        )

    def clean(self):
        cleaned_data = super().clean()
        # Remove the paste_button from cleaned data
        if "paste_button" in cleaned_data:
            del cleaned_data["paste_button"]
        return cleaned_data


class SearchForm(forms.Form):
    q = QueryField(required=False)


class PasteButtonWidget(forms.Widget):
    def render(self, name, value, attrs=None, renderer=None):
        info_label = '<p id="paste-screenshot-info-label" class="text-center"></p>'
        btn_text = gettext_lazy("Paste from clipboard")
        btn_template = f'<button id="paste-screenshot-btn" class="btn" type="button">{btn_text}</button>'
        return info_label + btn_template
