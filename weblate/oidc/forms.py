# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django import forms
from oauth2_provider.forms import AllowForm


class AuthorizationForm(AllowForm):
    weblate_consent = forms.BooleanField(initial=True, widget=forms.HiddenInput())
    max_age = forms.IntegerField(
        min_value=0, required=False, widget=forms.HiddenInput()
    )
