# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy, pgettext_lazy


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


class LibreTranslateMachineryForm(KeyURLMachineryForm):
    key = forms.CharField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API key"),
        required=False,
    )


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
        widget=forms.PasswordInput,
        required=False,
    )
    enable_mt = forms.BooleanField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Enable machine translation"
        ),
        required=False,
        initial=True,
    )
    domain = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Translation domain"
        ),
        help_text=gettext_lazy(
            "The ID of a translation domain, for example, BC. If you do not specify "
            "a domain, the method searches for translations in all available domains."
        ),
        required=False,
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
            ("api.cognitive.microsofttranslator.us", "Azure US Government cloud"),
        ),
    )
    endpoint_url = forms.ChoiceField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Authentication service URL"
        ),
        initial="api.cognitive.microsoft.com",
        choices=(
            ("api.cognitive.microsoft.com", "Global"),
            ("api.cognitive.azure.cn", "China"),
            ("api.cognitive.microsoft.us", "Azure US Government cloud"),
        ),
        help_text=gettext_lazy(
            "Regional or multi-service can be specified using region field below."
        ),
    )
    region = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Authentication service region",
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
            raise ValidationError(gettext("Could not parse JSON: %s") % error)
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
    formality = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Formality"
        ),
        help_text=gettext_lazy(
            "Uses the specified formality if language is not specified as (in)formal"
        ),
        widget=forms.Select(
            choices=(
                ("default ", "Default"),
                ("prefer_more", "Formal"),
                ("prefer_less", "Informal"),
            )
        ),
        initial="default",
        required=False,
    )
