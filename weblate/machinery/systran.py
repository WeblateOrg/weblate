# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from .base import (
    MACHINERY_DEFAULT_THRESHOLD,
    MachineTranslation,
    MachineTranslationError,
)
from .forms import KeyMachineryForm


class SystranTranslation(MachineTranslation):
    """Systran machine translation support."""

    name = "Systran"
    max_score = 90
    settings_form = KeyMachineryForm

    def get_headers(self) -> dict[str, str]:
        """Add authentication headers to request."""
        return {"Authorization": f"Key {self.settings['key']}"}

    def check_failure(self, response) -> None:
        if "error" not in response:
            return
        raise MachineTranslationError(response["error"]["message"])

    def download_languages(self):
        """Download list of supported languages from a service."""
        response = self.request(
            "get",
            "https://api-translate.systran.net/translation/supportedLanguages",
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
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ):
        """Download list of possible translations from a service."""
        response = self.request(
            "post",
            "https://api-translate.systran.net/translation/text/translate",
            params={
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
