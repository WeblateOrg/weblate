# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Seth Falco <seth@falco.fun>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from .base import BatchMachineTranslation, MachineTranslationError
from .forms import LibreTranslateMachineryForm

if TYPE_CHECKING:
    from weblate.trans.models import Unit

    from .base import DownloadMultipleTranslations


class BaseLibreTranslateTranslation(BatchMachineTranslation):
    """Base class for LibreTranslate-compatible machine translation services."""

    max_score = 89
    settings_form = LibreTranslateMachineryForm
    request_timeout = 20

    def download_languages(self):
        response = self.request(
            "get",
            self.get_api_url("languages"),
        )
        return [x["code"] for x in response.json()]

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-")

    def _parse_translated_texts(self, payload: object, texts: list[str]) -> list[str]:
        if not isinstance(payload, dict):
            msg = "Unexpected response from LibreTranslate"
            raise MachineTranslationError(msg)

        translated_texts = payload.get("translatedText")
        if isinstance(translated_texts, list) and all(
            isinstance(item, str) for item in translated_texts
        ):
            if len(translated_texts) != len(texts):
                msg = "Unexpected number of translations in LibreTranslate response"
                raise MachineTranslationError(msg)
            return translated_texts

        if len(texts) == 1 and isinstance(translated_texts, str):
            return [translated_texts]

        msg = "Unexpected translatedText in LibreTranslate response"
        raise MachineTranslationError(msg)

    def _request_translations(
        self,
        source_language: str,
        target_language: str,
        texts: list[str],
        *,
        scalar_query: bool = False,
    ) -> list[str]:
        response = self.request(
            "post",
            self.get_api_url("translate"),
            json={
                "api_key": self.settings["key"],
                "q": texts[0] if scalar_query else texts,
                "source": source_language,
                "target": target_language,
            },
        )
        return self._parse_translated_texts(response.json(), texts)

    def download_translated_texts(
        self,
        source_language: str,
        target_language: str,
        texts: list[str],
    ) -> list[str]:
        """Download translated texts from a service."""
        return self._request_translations(source_language, target_language, texts)

    def format_translations(
        self, texts: list[str], translated_texts: list[str]
    ) -> DownloadMultipleTranslations:
        """Format translated texts for Weblate machinery consumers."""
        return {
            text: [
                {
                    "text": translated_texts[index],
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                }
            ]
            for index, text in enumerate(texts)
        }

    def download_multiple_translations(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = 75,
    ) -> DownloadMultipleTranslations:
        """Download list of possible translations from a service."""
        texts = [text for text, _unit in sources]
        translated_texts = self.download_translated_texts(
            source_language, target_language, texts
        )
        return self.format_translations(texts, translated_texts)


class LibreTranslateTranslation(BaseLibreTranslateTranslation):
    """LibreTranslate machine translation support."""

    name = "LibreTranslate"
    trusted_error_hosts: ClassVar[set[str]] = {"libretranslate.com"}
    version_added = "4.7.1"


class LTEngineTranslation(BaseLibreTranslateTranslation):
    """LTEngine machine translation support."""

    name = "LTEngine"
    version_added = "5.17.1"
    batch_size = 1

    def download_translated_texts(
        self,
        source_language: str,
        target_language: str,
        texts: list[str],
    ) -> list[str]:
        """Download translated texts from a service."""
        return [
            self._request_translations(
                source_language, target_language, [text], scalar_query=True
            )[0]
            for text in texts
        ]
