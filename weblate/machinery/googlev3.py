# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from typing import Any

from django.utils.functional import cached_property
from google.cloud.translate import TranslationServiceClient
from google.oauth2 import service_account

from .base import XMLMachineTranslationMixin
from .forms import GoogleV3MachineryForm
from .google import GoogleBaseTranslation


class GoogleV3Translation(XMLMachineTranslationMixin, GoogleBaseTranslation):
    """Google Translate API v3 machine translation support."""

    setup = None
    name = "Google Cloud Translation Advanced"
    max_score = 90
    settings_form = GoogleV3MachineryForm

    @classmethod
    def get_identifier(cls):
        return "google-translate-api-v3"

    @cached_property
    def client(self):
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(self.settings["credentials"])
        )
        api_endpoint = "translate.googleapis.com"
        if self.settings["location"].startswith("europe-"):
            api_endpoint = "translate-eu.googleapis.com"
        elif self.settings["location"].startswith("us-"):
            api_endpoint = "translate-us.googleapis.com"
        return TranslationServiceClient(
            credentials=credentials, client_options={"api_endpoint": api_endpoint}
        )

    @cached_property
    def parent(self):
        project = self.settings["project"]
        location = self.settings["location"]
        return f"projects/{project}/locations/{location}"

    def download_languages(self):
        """List of supported languages."""
        response = self.client.get_supported_languages(request={"parent": self.parent})
        return [language.language_code for language in response.languages]

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ):
        """Download list of possible translations from a service."""
        request = {
            "parent": self.parent,
            "contents": [text],
            "target_language_code": language,
            "source_language_code": source,
            "mime_type": "text/html",
        }
        response = self.client.translate_text(request)

        yield {
            "text": response.translations[0].translated_text,
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }

    def format_replacement(self, h_start: int, h_end: int, h_text: str, h_kind: Any):
        """Generates a single replacement."""
        return f'<span translate="no" id="{h_start}">{self.escape_text(h_text)}</span>'  # noqa: B028

    def cleanup_text(self, text, unit):
        text, replacements = super().cleanup_text(text, unit)

        # Sanitize newlines
        replacement = '<br translate="no">'
        replacements[replacement] = "\n"

        return text.replace("\n", replacement), replacements
