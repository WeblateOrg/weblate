# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from dateutil.parser import isoparse
from django.core.cache import cache
from requests.exceptions import HTTPError, RequestException

from .base import (
    BatchMachineTranslation,
    DownloadMultipleTranslations,
    GlossaryDoesNotExistError,
    GlossaryMachineTranslationMixin,
    XMLMachineTranslationMixin,
)
from .forms import DeepLMachineryForm

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Unit


class DeepLTranslation(
    XMLMachineTranslationMixin, GlossaryMachineTranslationMixin, BatchMachineTranslation
):
    """DeepL (Linguee) machine translation support."""

    name = "DeepL"
    # This seems to be currently best MT service, so score it a bit
    # better than other ones.
    max_score = 91
    language_map = {
        "zh_Hans": "zh",
        "zh_Hant": "",  # Traditional Chinese not supported but would map to zh
        "pt": "pt-pt",
        "pt@formal": "pt-pt@formal",
        "pt@informal": "pt-pt@informal",
    }
    hightlight_syntax = True
    settings_form = DeepLMachineryForm
    glossary_count_limit = 1000

    @property
    def api_base_url(self):
        url = super().api_base_url
        if self.settings["key"].endswith(":fx") and url == "https://api.deepl.com/v2":
            return "https://api-free.deepl.com/v2"
        return url

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").upper()

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"DeepL-Auth-Key {self.settings['key']}"}

    def get_error_message(self, exc):
        if isinstance(exc, RequestException) and exc.response is not None:
            try:
                data = exc.response.json()
            except ValueError:
                pass
            else:
                try:
                    return data["message"]
                except KeyError:
                    pass

        if isinstance(exc, HTTPError) and exc.response.status_code == 456:
            return "Quota exceeded. The character limit has been reached."

        return super().get_error_message(exc)

    def download_languages(self):
        response = self.request(
            "get", self.get_api_url("languages"), params={"type": "source"}
        )
        source_languages = {x["language"] for x in response.json()}
        response = self.request(
            "get", self.get_api_url("languages"), params={"type": "target"}
        )
        # Plain English is not listed, but is supported
        target_languages = {"EN"}

        # Handle formality extensions
        for item in response.json():
            lang_code = item["language"].upper()
            target_languages.add(lang_code)
            if item.get("supports_formality"):
                target_languages.add(f"{lang_code}@FORMAL")
                target_languages.add(f"{lang_code}@INFORMAL")

        return (
            (source, target)
            for source in source_languages
            for target in target_languages
        )

    def is_supported(self, source_language, target_language):
        """Check whether given language combination is supported."""
        return (source_language, target_language) in self.supported_languages

    def download_multiple_translations(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user: User | None = None,
        threshold: int = 75,
    ) -> DownloadMultipleTranslations:
        """Download list of possible translations from a service."""
        texts = [text for text, _unit in sources]
        unit = sources[0][1]

        glossary_id = self.get_glossary_id(source_language, target_language, unit)

        params = {
            "text": texts,
            "source_lang": source_language,
            "target_lang": target_language,
            "formality": self.settings.get("formality", "default"),
            "tag_handling": "xml",
            "ignore_tags": ["x"],
        }
        if context := self.settings.get("context", ""):
            params["context"] = context
        if target_language.endswith("@FORMAL"):
            params["target_lang"] = target_language[:-7]
            params["formality"] = "more"
        elif target_language.endswith("@INFORMAL"):
            params["target_lang"] = target_language[:-9]
            params["formality"] = "less"
        if glossary_id is not None:
            params["glossary_id"] = glossary_id
        response = self.request(
            "post",
            self.get_api_url("translate"),
            json=params,
        )
        payload = response.json()

        result: DownloadMultipleTranslations = {}
        for index, text in enumerate(texts):
            result[text] = [
                {
                    "text": payload["translations"][index]["text"],
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                }
            ]
        return result

    def format_replacement(
        self, h_start: int, h_end: int, h_text: str, h_kind: Unit | None
    ) -> str:
        """Generate a single replacement."""
        return f'<x id="{h_start}"></x>'

    def is_glossary_supported(self, source_language: str, target_language: str) -> bool:
        cache_key = self.get_cache_key("glossary_languages")
        languages_cache = cache.get(cache_key)
        if languages_cache is not None:
            # hiredis-py 3 makes list from set
            languages = set(languages_cache)
        else:
            response = self.request("get", self.get_api_url("glossary-language-pairs"))
            languages = {
                (support["source_lang"].upper(), support["target_lang"].upper())
                for support in response.json()["supported_languages"]
            }

            cache.set(cache_key, languages, 24 * 3600)

        source_language = source_language.split("-")[0]
        target_language = target_language.split("-")[0]
        return (source_language, target_language) in languages

    def list_glossaries(self) -> dict[str, str]:
        response = self.request("get", self.get_api_url("glossaries"))
        return {
            glossary["name"]: glossary["glossary_id"]
            for glossary in response.json()["glossaries"]
        }

    def delete_oldest_glossary(self) -> None:
        response = self.request("get", self.get_api_url("glossaries"))
        glossaries = sorted(
            response.json()["glossaries"],
            key=lambda glossary: isoparse(glossary["creation_time"]),
        )
        if glossaries:
            self.delete_glossary(glossaries[0]["glossary_id"])

    def delete_glossary(self, glossary_id: str) -> None:
        """
        Delete glossary from service.

        :param glossary_id: ID of the glossary to delete
        :raises GlossaryDoesNotExistError: If the glossary does not exist
        """
        try:
            self.request("delete", self.get_api_url("glossaries", glossary_id))
        except HTTPError as error:
            if error.response.status_code in {400, 404}:
                raise GlossaryDoesNotExistError from error

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ) -> None:
        # Deepl gracefully handles glossaries with duplicate name by updating the existing one
        self.request(
            "post",
            self.get_api_url("glossaries"),
            json={
                "name": name,
                "source_lang": source_language.split("-")[0],
                "target_lang": target_language.split("-")[0],
                "entries": tsv,
                "entries_format": "tsv",
            },
        )
