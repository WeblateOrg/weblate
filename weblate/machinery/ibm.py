# Copyright © Kao, Ming-Yang <vincent0629@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from base64 import b64encode

from weblate.machinery.base import MachineTranslation

from .forms import KeyURLMachineryForm


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
    def get_identifier(cls):
        return "ibm"

    def get_authentication(self):
        """Hook for backends to allow add authentication headers to request."""
        b64 = str(b64encode(f"apikey:{self.settings['key']}".encode()), "UTF-8")
        return {
            "Authorization": f"Basic {b64}",
            "Content-Type": "application/json",
        }

    def download_languages(self):
        """Download list of supported languages from a service."""
        response = self.request(
            "get",
            f"{self.api_base_url}/v3/languages?version=2018-05-01",
        )
        return [x["language"] for x in response.json()["languages"]]

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
        response = self.request(
            "post",
            f"{self.api_base_url}/v3/translate?version=2018-05-01",
            json={
                "text": [text],
                "source": source,
                "target": language,
            },
        )
        yield {
            "text": response.json()["translations"][0]["translation"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
