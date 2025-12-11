# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from .base import MachineTranslation, MachineTranslationError
from .forms import KeyMachineryForm


class SystranTranslation(MachineTranslation):
    """Systran machine translation support."""

    name = "Systran"
    max_score = 90
    settings_form = KeyMachineryForm

    def check_failure(self, response) -> None:
        if "error" not in response:
            return
        raise MachineTranslationError(response["error"]["message"])

    def download_languages(self):
        """Download list of supported languages from a service."""
        response = self.request(
            "get",
            "https://api-translate.systran.net/translation/supportedLanguages",
            params={"key": self.settings["key"]},
        )
        payload = response.json()
        self.check_failure(payload)
        return [(item["source"], item["target"]) for item in payload["languagePairs"]]

    def is_supported(self, source_language, target_language):
        """Check whether given language combination is supported."""
        return (source_language, target_language) in self.supported_languages

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ):
        """Download list of possible translations from a service."""
        response = self.request(
            "post",
            "https://api-translate.systran.net/translation/text/translate",
            params={
                "key": self.settings["key"],
                "source": source_language,
                "target": target_language,
                "input": text,
            },
        )
        payload = response.json()

        self.check_failure(payload)

        for translation in payload["outputs"]:
            yield {
                "text": translation["output"],
                "quality": self.max_score,
                "service": self.name,
                "source": text,
            }
