# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import forms
from django.utils.translation import gettext_lazy


class HostingForm(forms.Form):
    """Form for asking for hosting."""

    message = forms.CharField(
        label=gettext_lazy("Additional message"),
        required=True,
        widget=forms.Textarea,
        max_length=1000,
        help_text=gettext_lazy(
            "Please describe the project and your relation to it, "
            "preferably in English."
        ),
    )
