# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import csv
import json
import os
import tempfile

from dateutil.parser import isoparse

import weblate.utils.version

from .base import (
    DownloadTranslations,
    GlossaryMachineTranslationMixin,
    MachineTranslationError,
)
from .forms import ModernMTMachineryForm


class ModernMTTranslation(GlossaryMachineTranslationMixin):
    """ModernMT machine translation support."""

    name = "ModernMT"
    max_score = 90
    settings_form = ModernMTMachineryForm

    language_map = {
        "fa": "pes",
        "pt": "pt-PT",
        "sr": "sr-Cyrl",
        "zh_Hant": "zh-TW",
        "zh_Hans": "zh-CN",
    }
    glossary_count_limit = 1000

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").split("@")[0]

    def get_headers(self) -> dict[str, str]:
        """Add authentication headers to request."""
        return {
            "MMT-ApiKey": self.settings["key"],
            "MMT-Platform": "Weblate",
            "MMT-PlatformVersion": weblate.utils.version.VERSION,
        }

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        return (source, language) in self.supported_languages

    def check_failure(self, response) -> None:
        super().check_failure(response)
        payload = response.json()

        if "error" in payload:
            raise MachineTranslationError(payload["error"]["message"])

    def download_languages(self):
        """List of supported languages."""
        response = self.request("get", self.get_api_url("languages"))
        payload = response.json()

        for source, targets in payload["data"].items():
            yield from ((source, target) for target in targets)

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        params = {"q": text, "source": source, "target": language}
        glossary_id: int | None = self.get_glossary_id(source, language, unit)

        if glossary_id:
            params["glossaries"] = str(glossary_id)

        if context_vector := self.settings.get("context_vector"):
            params["context_vector"] = context_vector

        response = self.request(
            "get",
            self.get_api_url("translate"),
            params=params,
        )
        payload = response.json()

        yield {
            "text": payload["data"]["translation"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }

    def get_error_message(self, exc):
        if hasattr(exc, "read"):
            content = exc.read()
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = {}

            try:
                return data["error"]["message"]
            except KeyError:
                pass

        return super().get_error_message(exc)

    def is_glossary_supported(self, source_language: str, target_language: str) -> bool:
        """Check whether given languages pair is supported by service glossaries."""
        return self.is_supported(source_language, target_language)

    def list_glossaries(self) -> dict[str, str]:
        """List all glossaries from service."""
        response = self.request("get", self.get_api_url("memories"))
        return {
            glossary["name"]: glossary["id"]
            for glossary in response.json()["data"]
            if self.match_name_format(glossary["name"])
        }

    def delete_glossary(self, glossary_id: str) -> None:
        """Delete single glossary."""
        self.request("delete", self.get_api_url("memories", str(glossary_id)))

    def delete_oldest_glossary(self) -> None:
        """Delete oldest glossary if any."""
        response = self.request("get", self.get_api_url("memories"))
        glossaries: list[dict] = sorted(
            [
                glossary
                for glossary in response.json()["data"]
                if self.match_name_format(glossary["name"])
            ],
            key=lambda glossary: isoparse(glossary["creationDate"]),
        )
        if glossaries:
            self.delete_glossary(glossaries[0]["id"])

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ) -> None:
        """
        Create glossary in service.

        Create a memory with the given name and the populate with tsv content.
        """
        response = self.request(
            "post",
            self.get_api_url("memories"),
            data={"name": name},
        )
        glossary_id: int = response.json()["data"]["id"]

        temp_filename = ""
        with tempfile.NamedTemporaryFile(
            suffix=".csv", mode="w", encoding="utf-8", delete=False
        ) as file_content:
            reader = csv.reader(tsv.splitlines(), delimiter="\t")
            writer = csv.writer(file_content)
            writer.writerow([source_language, target_language])  # mandatory header
            writer.writerows(reader)
            temp_filename = file_content.name

        try:
            with open(temp_filename, "rb") as file_content:
                response = self.request(
                    "post",
                    self.get_api_url("memories", str(glossary_id), "glossary"),
                    data={
                        "type": "unidirectional",
                    },
                    files={
                        "csv": file_content,
                    },
                )
        finally:
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)
