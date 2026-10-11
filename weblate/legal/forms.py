# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy


class TOSForm(forms.Form):
    confirm = forms.BooleanField(
        label=gettext_lazy("I agree with the General Terms and Conditions document"),
        required=True,
    )
    next = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, include_privacy_policy: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if include_privacy_policy:
            self.fields["confirm"].label = gettext_lazy(
                "I agree with the General Terms and Conditions and the Privacy Policy"
            )
