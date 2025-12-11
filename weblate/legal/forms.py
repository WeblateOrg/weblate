# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import forms
from django.utils.translation import gettext_lazy


class TOSForm(forms.Form):
    confirm = forms.BooleanField(
        label=gettext_lazy("I agree with the General Terms and Conditions document"),
        required=True,
    )
    next = forms.CharField(required=False, widget=forms.HiddenInput)
