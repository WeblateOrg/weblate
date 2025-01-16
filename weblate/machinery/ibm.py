# Copyright © Kao, Ming-Yang <vincent0629@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import DownloadTranslations, MachineTranslation
from .forms import KeyURLMachineryForm

if TYPE_CHECKING:
    from requests.auth import AuthBase


class IBMTranslation(MachineTranslation):
    """IBM Watson Language Translator support."""

    name = "IBM Watson Language Translator"
    max_score = 88
    language_map = {
        "zh_Hant": "zh-TW",
        "zh_Hans": "zh",
    }
    settings_form = KeyURLMachineryForm

    @classmethod
    def get_identifier(cls) -> str:
        return "ibm"

    def get_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def get_auth(self) -> tuple[str, str] | AuthBase | None:
        return ("apikey", self.settings["key"])

    def download_languages(self):
        """Download list of supported languages from a service."""
        response = self.request(
            "get",
            f"{self.api_base_url}/v3/languages?version=2018-05-01",
        )
        return [x["language"] for x in response.json()["languages"]]

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
        response = self.request(
            "post",
            f"{self.api_base_url}/v3/translate?version=2018-05-01",
            json={
                "text": [text],
                "source": source_language,
                "target": target_language,
            },
        )
        yield {
            "text": response.json()["translations"][0]["translation"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
