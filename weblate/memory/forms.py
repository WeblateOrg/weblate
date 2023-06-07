# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import forms
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy


class UploadForm(forms.Form):
    """Uploading file to a translation memory."""

    file = forms.FileField(
        label=gettext_lazy("File"),
        validators=[FileExtensionValidator(allowed_extensions=["json", "tmx"])],
        help_text=gettext_lazy("You can upload a TMX or JSON file."),
    )


class DeleteForm(forms.Form):
    confirm = forms.BooleanField(
        label=gettext_lazy("Confirm deleting all translation memory entries"),
        required=True,
    )
