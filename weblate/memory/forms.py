# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import forms
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _


class UploadForm(forms.Form):
    """Uploading file to a translation memory."""

    file = forms.FileField(
        label=_("File"),
        validators=[FileExtensionValidator(allowed_extensions=["json", "tmx"])],
        help_text=_("You can upload a TMX or JSON file."),
    )


class DeleteForm(forms.Form):
    confirm = forms.BooleanField(
        label=_("Confirm deleting all translation memory entries"), required=True
    )
