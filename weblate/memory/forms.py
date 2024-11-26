# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import PurePath

from django import forms
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy

from weblate.lang.models import Language
from weblate.utils.forms import SortedSelect


class UploadForm(forms.Form):
    """Uploading file to a translation memory."""

    file = forms.FileField(
        label=gettext_lazy("File"),
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "json",
                    "tmx",
                    "xliff",
                    "po",
                    "csv",
                ]
            )
        ],
        help_text=gettext_lazy(
            "You can upload a file of following formats: TMX, JSON, XLIFF, PO, CSV."
        ),
    )
    source_language = forms.ModelChoiceField(
        widget=SortedSelect,
        label=gettext_lazy("Source language"),
        help_text=gettext_lazy(
            "Source language of the document when not specified in file"
        ),
        queryset=Language.objects.all(),
        required=False,
    )
    target_language = forms.ModelChoiceField(
        widget=SortedSelect,
        label=gettext_lazy("Target language"),
        help_text=gettext_lazy(
            "Target language of the document when not specified in file"
        ),
        queryset=Language.objects.all(),
        required=False,
    )

    def clean(self):
        data = self.cleaned_data
        extension = PurePath(data["file"].name).suffix[1:].lower()
        if extension in {"xliff", "po", "csv"} and not all(
            [data["source_language"], data["target_language"]]
        ):
            raise forms.ValidationError(
                gettext_lazy(
                    "Source language and target language must be specified for this file format."
                ),
                code="missing_languages",
            )
        return data


class DeleteForm(forms.Form):
    confirm = forms.BooleanField(
        label=gettext_lazy("Confirm deleting all translation memory entries"),
        required=True,
    )
