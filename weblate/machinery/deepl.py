# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
from html import escape, unescape

from .base import MachineTranslation
from .forms import DeepLMachineryForm


class DeepLTranslation(MachineTranslation):
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
            lang_code = item["language"]
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

    # using custom cache key to ensure that formal and informal suggestions are cached separately
    def translate_cache_key(self, source, language, text, threshold):
        key = super().translate_cache_key(source, language, text, threshold)
        formality = self.settings.get("formality", "default")
        return f"{key}:{formality}"

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
        params = {
            "text": text,
            "source_lang": source,
            "target_lang": language,
            "formality": self.settings.get("formality", "default"),
            "tag_handling": "xml",
            "ignore_tags": "x",
        }
        if language.endswith("@FORMAL"):
            params["target_lang"] = language[:-7]
            params["formality"] = "more"
        elif language.endswith("@INFORMAL"):
            params["target_lang"] = language[:-9]
            params["formality"] = "less"
        response = self.request(
            "post",
            self.get_api_url("translate"),
            data=params,
        )
        payload = response.json()

        for translation in payload["translations"]:
            yield {
                "text": translation["text"],
                "quality": self.max_score,
                "service": self.name,
                "source": text,
            }

    def unescape_text(self, text: str):
        """Unescaping of the text with replacements."""
        return unescape(text)

    def escape_text(self, text: str):
        """Escaping of the text with replacements."""
        return escape(text)

    def format_replacement(self, h_start: int, h_end: int, h_text: str):
        """Generates a single replacement."""
        return f'<x id="{h_start}"></x>'  # noqa: B028

    def make_re_placeholder(self, text: str):
        return re.escape(text)
