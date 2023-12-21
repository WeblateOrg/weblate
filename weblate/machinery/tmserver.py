# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from requests.exceptions import HTTPError

from .base import MachineTranslation
from .forms import URLMachineryForm

AMAGAMA_LIVE = "https://amagama-live.translatehouse.org/api/v1"


class TMServerTranslation(MachineTranslation):
    """tmserver machine translation support."""

    name = "tmserver"
    settings_form = URLMachineryForm

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("-", "_").lower()

    def download_languages(self):
        """Download list of supported languages from a service."""
        try:
            # This URL needs trailing slash, that's why blank string is included
            response = self.request("get", self.get_api_url("languages", ""))
            data = response.json()
        except HTTPError as error:
            if error.response.status_code == 404:
                return []
            raise
        return [
            (src, tgt)
            for src in data["sourceLanguages"]
            for tgt in data["targetLanguages"]
        ]

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        if not self.supported_languages:
            # Fallback for old tmserver which does not export list of
            # supported languages
            return True
        return (source, language) in self.supported_languages

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
        url = self.get_api_url(
            source, language, "unit", text[:500].replace("\r", " ").encode()
        )
        response = self.request("get", url)
        payload = response.json()

        for line in payload:
            quality = int(line["quality"])
            if quality < threshold:
                continue
            yield {
                "text": line["target"],
                "quality": quality,
                "service": self.name,
                "source": line["source"],
            }


class AmagamaTranslation(TMServerTranslation):
    """Specific instance of tmserver ran by Virtaal authors."""

    name = "Amagama"
    settings_form = None

    @property
    def api_base_url(self):
        return AMAGAMA_LIVE
