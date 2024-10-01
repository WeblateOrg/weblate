# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from requests.exceptions import RequestException

from .base import DownloadTranslations, MachineTranslation, MachineTranslationError
from .forms import KeyMachineryForm

GOOGLE_API_ROOT = "https://translation.googleapis.com/language/translate/v2/"


class GoogleBaseTranslation(MachineTranslation):
    # Map codes used by Google to the ones used by Weblate
    language_map = {
        "nb": "no",
        "nb_NO": "no",
        "fil": "tl",
        "zh_Hant": "zh-TW",
        "zh_Hans": "zh-CN",
        "ber-Latn": "kab",  # Adding Kabyle language by mapping Tamazight latin
    }
    language_aliases = ({"zh-CN", "zh"},)

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").split("@")[0]

    def is_supported(self, source, language):
        # Avoid translation between aliases
        return super().is_supported(source, language) and not any(
            {source, language} == item for item in self.language_aliases
        )


class GoogleTranslation(GoogleBaseTranslation):
    """Google Translate API v2 machine translation support."""

    name = "Google Cloud Translation Basic"
    max_score = 90
    settings_form = KeyMachineryForm

    @classmethod
    def get_identifier(cls) -> str:
        return "google-translate"

    def check_failure(self, response) -> None:
        super().check_failure(response)
        payload = response.json()

        if "error" in payload:
            raise MachineTranslationError(payload["error"]["message"])

    def download_languages(self):
        """List of supported languages."""
        response = self.request(
            "get", GOOGLE_API_ROOT + "languages", params={"key": self.settings["key"]}
        )
        payload = response.json()

        return [d["language"] for d in payload["data"]["languages"]]

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
        response = self.request(
            "get",
            GOOGLE_API_ROOT,
            params={
                "key": self.settings["key"],
                "q": text,
                "source": source,
                "target": language,
                "format": "text",
            },
        )
        payload = response.json()

        translation = payload["data"]["translations"][0]["translatedText"]

        yield {
            "text": translation,
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }

    def get_error_message(self, exc):
        if isinstance(exc, RequestException) and exc.response is not None:
            data = exc.response.json()
            try:
                return data["error"]["message"]
            except KeyError:
                pass

        return super().get_error_message(exc)
