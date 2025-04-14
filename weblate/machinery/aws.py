# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


import operator

from django.utils.functional import cached_property

from .base import (
    DownloadTranslations,
    GlossaryDoesNotExistError,
    GlossaryMachineTranslationMixin,
)
from .forms import AWSMachineryForm


class AWSTranslation(GlossaryMachineTranslationMixin):
    """AWS machine translation."""

    name = "Amazon Translate"
    max_score = 88
    language_map = {
        "zh_Hant": "zh-TW",
        "zh_Hans": "zh",
        "nb_NO": "no",
    }
    settings_form = AWSMachineryForm

    # glossary name must match the pattern ^([A-Za-z0-9-]_?)+$
    glossary_name_format = (
        "weblate_-_{project}_-_{source_language}_-_{target_language}_-_{checksum}"
    )

    glossary_count_limit = 100

    @classmethod
    def get_identifier(cls) -> str:
        return "aws"

    @cached_property
    def client(self):
        import boto3

        return boto3.client(
            service_name="translate",
            region_name=self.settings["region"],
            aws_access_key_id=self.settings["key"],
            aws_secret_access_key=self.settings["secret"],
        )

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").split("@")[0]

    def download_languages(self):
        """List of supported languages."""
        result = self.client.list_languages()
        return [lang["LanguageCode"] for lang in result["Languages"]]

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ) -> DownloadTranslations:
        params = {
            "Text": text,
            "SourceLanguageCode": source_language,
            "TargetLanguageCode": target_language,
        }

        glossary_name: str | None = self.get_glossary_id(
            source_language, target_language, unit
        )
        if glossary_name:
            params["TerminologyNames"] = [glossary_name]

        response = self.client.translate_text(**params)
        yield {
            "text": response["TranslatedText"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ) -> None:
        """Create glossary in the service."""
        # add header with source and target languages
        tsv = f"{source_language}\t{target_language}\n{tsv}"

        # AWS gracefully handles duplicate entries by merging them
        self.client.import_terminology(
            Name=name,
            MergeStrategy="OVERWRITE",
            TerminologyData={
                "File": tsv.encode(),
                "Format": "TSV",
                "Directionality": "UNI",
            },
        )

    def is_glossary_supported(self, source_language: str, target_language: str) -> bool:
        """Check whether given language combination is supported for glossary."""
        return self.is_supported(source_language, target_language)

    def list_glossaries(self) -> dict[str, str]:
        """List all glossaries from service."""
        result = (
            self.client.get_paginator("list_terminologies")
            .paginate()
            .build_full_result()
        )
        return {
            terminology["Name"]: terminology["Name"]
            for terminology in result["TerminologyPropertiesList"]
        }

    def delete_glossary(self, glossary_id: str) -> None:
        """Delete a single glossary from service."""
        try:
            self.client.delete_terminology(Name=glossary_id)
        except self.client.exceptions.ResourceNotFoundException as error:
            raise GlossaryDoesNotExistError from error

    def delete_oldest_glossary(self) -> None:
        """Delete oldest glossary if any."""
        result = (
            self.client.get_paginator("list_terminologies")
            .paginate()
            .build_full_result()
        )
        glossaries = sorted(
            result["TerminologyPropertiesList"],
            key=operator.itemgetter("CreatedAt"),
        )
        if glossaries:
            self.delete_glossary(glossaries[0]["Name"])
