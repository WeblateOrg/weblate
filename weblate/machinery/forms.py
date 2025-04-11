# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy, pgettext_lazy

from weblate.utils.forms import WeblateServiceURLField

from .types import SourceLanguageChoices


class BaseMachineryForm(forms.Form):
    source_language = forms.ChoiceField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Source language selection"
        ),
        choices=SourceLanguageChoices,
        initial=SourceLanguageChoices.AUTO,
        required=False,
    )

    def __init__(self, machinery, *args, **kwargs) -> None:
        self.machinery = machinery
        super().__init__(*args, **kwargs)

    def serialize_form(self):
        return self.cleaned_data

    def clean(self) -> None:
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
    url = WeblateServiceURLField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API URL"),
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

    def clean(self) -> None:
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
    category = forms.CharField(
        label=pgettext_lazy("Automatic suggestion service configuration", "Category"),
        help_text=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Specify a customized system category ID to use it instead of general one.",
        ),
        initial="general",
        required=False,
    )


class GoogleV3MachineryForm(BaseMachineryForm):
    credentials = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Google Translate service account info",
        ),
        widget=forms.Textarea,
        help_text=pgettext_lazy(
            "Google Cloud Translation configuration",
            "Enter a JSON key for the service account.",
        ),
    )
    project = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Google Translate project"
        ),
        help_text=pgettext_lazy(
            "Google Cloud Translation configuration",
            "Enter the numeric or alphanumeric ID of your Google Cloud project.",
        ),
    )
    location = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Google Translate location"
        ),
        initial="global",
        help_text=pgettext_lazy(
            "Google Cloud Translation configuration",
            "Choose a Google Cloud Translation region that is used for the Google Cloud project or is closest to you.",
        ),
        widget=forms.Select(
            choices=(
                ("global ", pgettext_lazy("Google Cloud region", "Global")),
                ("europe-west1 ", pgettext_lazy("Google Cloud region", "Europe")),
                ("us-west1", pgettext_lazy("Google Cloud region", "US")),
            )
        ),
    )
    bucket_name = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Google Storage Bucket name"
        ),
        help_text=pgettext_lazy(
            "Google Cloud Translation configuration",
            "Enter the name of the Google Cloud Storage bucket that is used to store the Glossary files.",
        ),
        required=False,
    )

    def clean_credentials(self):
        try:
            json.loads(self.cleaned_data["credentials"])
        except json.JSONDecodeError as error:
            raise ValidationError(
                gettext("Could not parse JSON: %s") % error
            ) from error
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


class AlibabaMachineryForm(KeySecretMachineryForm):
    key = forms.CharField(
        label=pgettext_lazy("Alibaba Translate configuration", "Access key ID")
    )
    secret = forms.CharField(
        label=pgettext_lazy("Alibaba Translate configuration", "Access key secret")
    )
    region = forms.CharField(
        label=pgettext_lazy("Alibaba Translate configuration", "Region ID")
    )


class ModernMTMachineryForm(KeyURLMachineryForm):
    url = WeblateServiceURLField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API URL"),
        initial="https://api.modernmt.com/",
    )
    context_vector = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Context vector"
        ),
        help_text=gettext_lazy(
            "Comma-separated list of memory IDs:weight. e.g: 1234:0.123,4567:0.456"
        ),
        required=False,
    )

    def clean_context_vector(self):
        """Validate context_vector field."""
        pattern = r"^\d+:\d(?:\.\d{1,3})?$"
        context_vector = self.cleaned_data["context_vector"]
        if context_vector:
            for couple in context_vector.split(","):
                if not re.match(pattern, couple):
                    raise ValidationError(
                        gettext("The context vector is not valid: %s") % couple
                    )
                if not 0 < (weight := float(couple.split(":")[1])) < 1:
                    raise ValidationError(
                        gettext("The weight value must be between 0 and 1: %s") % weight
                    )
        return self.cleaned_data["context_vector"]


class DeepLMachineryForm(KeyURLMachineryForm):
    url = WeblateServiceURLField(
        label=pgettext_lazy("Automatic suggestion service configuration", "API URL"),
        initial="https://api.deepl.com/v2/",
    )
    formality = forms.CharField(
        label=pgettext_lazy("Automatic suggestion service configuration", "Formality"),
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
    context = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Translation context",
        ),
        widget=forms.Textarea,
        help_text=gettext_lazy(
            "Describe the context of the translation to improve the accuracy of the translation."
        ),
        required=False,
    )


class BaseOpenAIMachineryForm(KeyMachineryForm):
    persona = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Translator persona",
        ),
        widget=forms.Textarea,
        help_text=gettext_lazy(
            "Describe the persona of translator to improve the accuracy of the translation. For example: “You are a squirrel breeder.”"
        ),
        required=False,
    )
    style = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Translator style",
        ),
        widget=forms.Textarea,
        help_text=gettext_lazy(
            "Describe the style of translation. For example: “Use informal language.”"
        ),
        required=False,
    )


class OpenAIMachineryForm(BaseOpenAIMachineryForm):
    # Ordering choices here defines priority for automatic selection
    MODEL_CHOICES = (
        ("auto", pgettext_lazy("OpenAI model selection", "Automatic selection")),
        ("gpt-4o-mini", "GPT-4o mini"),
        ("gpt-4o", "GPT-4o"),
        ("o3-mini", "OpenAI o3-mini"),
        ("o3", "OpenAI o3"),
        ("o1-mini", "OpenAI o1-mini"),
        ("o1", "OpenAI o1"),
        ("gpt-4.5-preview", "GPT-4.5"),
        ("gpt-4-turbo", "GPT-4 Turbo"),
        ("gpt-4", "GPT-4"),
        ("gpt-3.5-turbo", "GPT-3.5 Turbo"),
        ("custom", pgettext_lazy("OpenAI model selection", "Custom model")),
    )
    base_url = WeblateServiceURLField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "OpenAI API base URL",
        ),
        widget=forms.TextInput,
        help_text=gettext_lazy(
            "Base URL of the OpenAI API, if it differs from the OpenAI default URL"
        ),
        required=False,
    )
    model = forms.ChoiceField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "OpenAI model",
        ),
        initial="auto",
        choices=MODEL_CHOICES,
    )
    custom_model = forms.CharField(
        label=pgettext_lazy(
            "OpenAI model selection",
            "Custom model name",
        ),
        help_text=gettext_lazy("Only needed when model is set to 'Custom model'"),
        required=False,
    )

    def clean(self) -> None:
        """Validate `custom_model, model` fields."""
        has_custom_model = bool(self.cleaned_data.get("custom_model"))
        model = self.cleaned_data.get("model")
        if model == "custom" and not has_custom_model:
            raise ValidationError(
                {"custom_model": gettext("Missing custom model name.")}
            )
        if model != "custom" and has_custom_model:
            raise ValidationError(
                {"model": gettext("Choose custom model here to enable it.")}
            )
        super().clean()


class AzureOpenAIMachineryForm(BaseOpenAIMachineryForm):
    azure_endpoint = WeblateServiceURLField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Azure OpenAI endpoint URL",
        ),
        widget=forms.TextInput,
        help_text=gettext_lazy(
            "Endpoint URL of the instance, e.g: https://my-instance.openai.azure.com."
        ),
    )
    deployment = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Azure OpenAI deployment",
        ),
        widget=forms.TextInput,
        help_text=gettext_lazy("The model's unique deployment name."),
    )
