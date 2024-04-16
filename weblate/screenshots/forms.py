# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import forms

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
        # This is overriden from initial arg of the form
        self.fields["translation"].initial = component.source_translation
        self.fields["translation"].empty_label = None


class SearchForm(forms.Form):
    q = QueryField(required=False)
