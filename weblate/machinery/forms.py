#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, pgettext_lazy


class BaseMachineryForm(forms.Form):
    def __init__(self, machinery, *args, **kwargs):
        self.machinery = machinery
        super().__init__(*args, **kwargs)

    def serialize_form(self):
        return self.cleaned_data

    def clean(self):
        settings = self.serialize_form()
        for field, data in self.fields.items():
            if not data.required:
                continue
            if field not in settings:
                return
        machinery = self.machinery(settings)
        machinery.validate_settings()


class KeyMachineryForm(BaseMachineryForm):
    key = forms.CharField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API key")
    )


class URLMachineryForm(BaseMachineryForm):
    url = forms.URLField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API URL")
    )


class KeySecretMachineryForm(KeyMachineryForm):
    key = forms.CharField(
        label=pgettext_lazy("Automatic suggestion service configuration", "Client ID")
    )
    secret = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Client secret"
        )
    )


class KeyURLMachineryForm(KeyMachineryForm, URLMachineryForm):
    pass


class MyMemoryMachineryForm(BaseMachineryForm):
    email = forms.EmailField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Contact e-mail"
        ),
        required=False,
    )
    username = forms.CharField(
        label=pgettext_lazy("Automatic suggestion service configuration", "Username"),
        required=False,
    )
    key = forms.CharField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API key"),
        required=False,
    )


class SAPMachineryForm(URLMachineryForm):
    key = forms.CharField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API key"),
        required=False,
    )
    username = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "SAP username"
        ),
        required=False,
    )
    password = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "SAP password"
        ),
        required=False,
    )
    enable_mt = forms.BooleanField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Enable machine translation"
        ),
        required=False,
        initial=True,
    )

    def clean(self):
        has_sandbox = bool(self.cleaned_data.get("key"))
        has_production = self.cleaned_data.get("username") and self.cleaned_data.get(
            "password"
        )
        if not has_sandbox and not has_production:
            raise ValidationError(
                gettext("Please provide either key or username and password.")
            )
        super().clean()


class MicrosoftMachineryForm(KeyMachineryForm):
    endpoint_url = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Application endpoint URL"
        ),
        initial="api.cognitive.microsoft.com",
    )
    base_url = forms.ChoiceField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Application base URL"
        ),
        initial="api.cognitive.microsofttranslator.com",
        choices=(
            ("api.cognitive.microsofttranslator.com", "Global (non-regional)"),
            ("api-apc.cognitive.microsofttranslator.com", "Asia Pacific"),
            ("api-eur.cognitive.microsofttranslator.com", "Europe"),
            ("api-nam.cognitive.microsofttranslator.com", "North America"),
            ("api.translator.azure.cn", "China"),
        ),
    )
    region = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Application region"
        ),
        required=False,
    )


class GoogleV3MachineryForm(BaseMachineryForm):
    credentials = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Google Translate service account info",
        ),
        widget=forms.Textarea,
    )
    project = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Google Translate project"
        ),
    )
    location = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Google Translate location"
        ),
        initial="global",
    )

    def clean_credentials(self):
        try:
            json.loads(self.cleaned_data["credentials"])
        except json.JSONDecodeError as error:
            raise ValidationError(gettext("Failed to parse JSON: %s") % error)
        return self.cleaned_data["credentials"]


class AWSMachineryForm(KeySecretMachineryForm):
    key = forms.CharField(
        label=pgettext_lazy("AWS Translate configuration", "Access key ID")
    )
    secret = forms.CharField(
        label=pgettext_lazy("AWS Translate configuration", "API secret key")
    )
    region = forms.CharField(
        label=pgettext_lazy("AWS Translate configuration", "Region name")
    )


class ModernMTMachineryForm(KeyURLMachineryForm):
    url = forms.URLField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API URL"),
        initial="https://api.modernmt.com/",
    )


class DeepLMachineryForm(KeyURLMachineryForm):
    url = forms.URLField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API URL"),
        initial="https://api.deepl.com/v2/",
    )
