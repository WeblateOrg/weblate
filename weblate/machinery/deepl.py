# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dateutil.parser import isoparse
from django.core.cache import cache

from .base import (
    BatchMachineTranslation,
    GlossaryMachineTranslationMixin,
    XMLMachineTranslationMixin,
)
from .forms import DeepLMachineryForm

if TYPE_CHECKING:
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
        "zh_hans": "zh",
        "pt": "pt-pt",
    }
    force_uncleanup = True
    hightlight_syntax = True
    settings_form = DeepLMachineryForm
    glossary_count_limit = 1000

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").upper()

    def get_authentication(self):
        return {"Authorization": f"DeepL-Auth-Key {self.settings['key']}"}

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

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        return (source, language) in self.supported_languages

    def download_multiple_translations(
        self,
        source,
        language,
        sources: list[tuple[str, Unit]],
        user=None,
        threshold: int = 75,
    ) -> dict[str, list[dict[str, str]]]:
        """Download list of possible translations from a service."""
        texts = [text for text, _unit in sources]
        unit = sources[0][1]

        glossary_id = self.get_glossary_id(source, language, unit)

        params = {
            "text": texts,
            "source_lang": source,
            "target_lang": language,
            "formality": self.settings.get("formality", "default"),
            "tag_handling": "xml",
            "ignore_tags": ["x"],
        }
        if language.endswith("@FORMAL"):
            params["target_lang"] = language[:-7]
            params["formality"] = "more"
        elif language.endswith("@INFORMAL"):
            params["target_lang"] = language[:-9]
            params["formality"] = "less"
        if glossary_id is not None:
            params["glossary_id"] = glossary_id
        response = self.request(
            "post",
            self.get_api_url("translate"),
            json=params,
        )
        payload = response.json()

        result = {}
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

    def format_replacement(self, h_start: int, h_end: int, h_text: str, h_kind: Any):
        """Generates a single replacement."""
        return f'<x id="{h_start}"></x>'  # noqa: B028

    def is_glossary_supported(self, source_language: str, target_language: str) -> bool:
        cache_key = self.get_cache_key("glossary_languages")
        languages = cache.get(cache_key)
        if languages is None:
            response = self.request("get", self.get_api_url("glossary-language-pairs"))
            languages = [
                (support["source_lang"].upper(), support["target_lang"].upper())
                for support in response.json()["supported_languages"]
            ]

            cache.set(cache_key, languages, 24 * 3600)

        source_language = source_language.split("-")[0]
        target_language = target_language.split("-")[0]
        return (source_language, target_language) in languages

    def list_glossaries(self) -> dict[str:str]:
        response = self.request("get", self.get_api_url("glossaries"))
        return {
            glossary["name"]: glossary["glossary_id"]
            for glossary in response.json()["glossaries"]
        }

    def delete_oldest_glossary(self):
        response = self.request("get", self.get_api_url("glossaries"))
        glossaries = sorted(
            response.json()["glossaries"],
            key=lambda glossary: isoparse(glossary["creation_time"]),
        )
        if glossaries:
            self.delete_glossary(glossaries[0]["glossary_id"])

    def delete_glossary(self, glossary_id: str):
        self.request("delete", self.get_api_url("glossaries", glossary_id))

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ):
        self.request(
            "post",
            self.get_api_url("glossaries"),
            json={
                "name": name,
                "source_lang": source_language,
                "target_lang": target_language,
                "entries": tsv,
                "entries_format": "tsv",
            },
        )
