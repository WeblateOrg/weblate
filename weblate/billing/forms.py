# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from crispy_forms.helper import FormHelper
from django import forms
from django.utils.translation import gettext_lazy

from weblate.utils.forms import UserField

from .models import Billing


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


class BillingMergeForm(forms.Form):
    other = forms.ModelChoiceField(
        queryset=Billing.objects.all(),
        label="Merge with billing",
        widget=forms.NumberInput,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False


class BillingMergeConfirmForm(BillingMergeForm):
    confirm = forms.BooleanField(required=True, label="Confirm merge")


class BillingUserForm(forms.Form):
    user = UserField(label=gettext_lazy("Add billing admin"), required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
