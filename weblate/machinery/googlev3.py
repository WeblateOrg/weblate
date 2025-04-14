# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import operator
from typing import TYPE_CHECKING

from django.utils.functional import cached_property
from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud import storage
from google.cloud.translate_v3 import (
    GcsSource,
    Glossary,
    GlossaryInputConfig,
    TranslateTextGlossaryConfig,
    TranslationServiceClient,
)
from google.oauth2 import service_account

from .base import (
    DownloadTranslations,
    GlossaryAlreadyExistsError,
    GlossaryDoesNotExistError,
    GlossaryMachineTranslationMixin,
    XMLMachineTranslationMixin,
)
from .forms import GoogleV3MachineryForm
from .google import GoogleBaseTranslation

if TYPE_CHECKING:
    from weblate.trans.models import Unit


class GoogleV3Translation(
    XMLMachineTranslationMixin, GoogleBaseTranslation, GlossaryMachineTranslationMixin
):
    """Google Translate API v3 machine translation support."""

    name = "Google Cloud Translation Advanced"
    max_score = 90
    settings_form = GoogleV3MachineryForm

    # estimation, actual limit is 10.4 million (10,485,760) UTF-8 bytes
    glossary_count_limit = 1000

    # Identifier must contain only lowercase letters, digits, or hyphens.
    glossary_name_format = (
        "weblate__{project}__{source_language}__{target_language}__{checksum}"
    )

    @classmethod
    def get_identifier(cls) -> str:
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
    def storage_client(self):
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(self.settings["credentials"])
        )
        return storage.Client(credentials=credentials)

    @cached_property
    def storage_bucket(self):
        return self.storage_client.get_bucket(self.settings["bucket_name"])

    @cached_property
    def parent(self) -> str:
        project = self.settings["project"]
        location = self.settings["location"]
        return f"projects/{project}/locations/{location}"

    def download_languages(self):
        """List of supported languages."""
        response = self.client.get_supported_languages(request={"parent": self.parent})
        return [language.language_code for language in response.languages]

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        request = {
            "parent": self.parent,
            "contents": [text],
            "target_language_code": target_language,
            "source_language_code": source_language,
            "mime_type": "text/html",
        }
        glossary_path: str | None = None
        if self.settings.get("bucket_name"):
            glossary_path = self.get_glossary_id(source_language, target_language, unit)
            request["glossary_config"] = TranslateTextGlossaryConfig(
                glossary=glossary_path
            )

        response = self.client.translate_text(request)

        response_translations = (
            response.glossary_translations if glossary_path else response.translations
        )

        yield {
            "text": response_translations[0].translated_text,
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }

    def format_replacement(
        self, h_start: int, h_end: int, h_text: str, h_kind: Unit | None
    ) -> str:
        """Generate a single replacement."""
        return f'<span translate="no" id="{h_start}">{self.escape_text(h_text)}</span>'

    def cleanup_text(self, text, unit):
        text, replacements = super().cleanup_text(text, unit)

        # Sanitize newlines
        replacement = '<br translate="no">'
        replacements[replacement] = "\n"

        return text.replace("\n", replacement), replacements

    def list_glossaries(self) -> dict[str, str]:
        """Return dictionary with the name/id of the glossary as the key and value."""
        return {
            glossary.display_name: glossary.display_name
            for glossary in self.client.list_glossaries(parent=self.parent)
        }

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ) -> None:
        """
        Create glossary in the service.

        - Uploads the TSV file to gcs bucket
        - Creates the glossary in the service
        """
        # upload tsv to storage bucket
        glossary_bucket_file = self.storage_bucket.blob(f"{name}.tsv")
        glossary_bucket_file.upload_from_string(
            tsv, content_type="text/tab-separated-values"
        )
        # create glossary
        bucket_name = self.settings["bucket_name"]
        gcs_source = GcsSource(input_uri=f"gs://{bucket_name}/{name}.tsv")
        input_config = GlossaryInputConfig(gcs_source=gcs_source)

        glossary = Glossary(
            name=self.get_glossary_resource_path(name),
            language_pair=Glossary.LanguageCodePair(
                source_language_code=source_language,
                target_language_code=target_language,
            ),
            input_config=input_config,
        )
        try:
            self.client.create_glossary(parent=self.parent, glossary=glossary)
        except AlreadyExists as error:
            raise GlossaryAlreadyExistsError from error

    def delete_glossary(self, glossary_name: str) -> None:
        """Delete the glossary in service and storage bucket."""
        try:
            self.client.delete_glossary(
                name=self.get_glossary_resource_path(glossary_name)
            )
        except NotFound as error:
            raise GlossaryDoesNotExistError from error
        finally:
            try:
                #  delete tsv from storage bucket
                glossary_bucket_file = self.storage_bucket.blob(f"{glossary_name}.tsv")
                glossary_bucket_file.delete()
            except NotFound:
                pass

    def delete_oldest_glossary(self) -> None:
        """Delete the oldest glossary if any."""
        glossaries = sorted(
            self.client.list_glossaries(parent=self.parent),
            key=operator.attrgetter("submit_time"),
        )
        if glossaries:
            self.delete_glossary(glossaries[0].display_name)

    def get_glossary_resource_path(self, glossary_name: str):
        """Return the resource path used by the Translation API."""
        return self.client.glossary_path(
            self.settings["project"], self.settings["location"], glossary_name
        )
