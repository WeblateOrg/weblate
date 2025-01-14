# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from .base import DownloadTranslations, MachineTranslation, MachineTranslationError
from .forms import KeyMachineryForm


class YandexTranslation(MachineTranslation):
    """Yandex machine translation support."""

    name = "Yandex"
    max_score = 90
    settings_form = KeyMachineryForm

    def check_failure(self, response) -> None:
        super().check_failure(response)
        payload = response.json()
        if "message" in payload:
            raise MachineTranslationError(payload["message"])
        if "code" in payload and payload["code"] != 200:
            msg = "Error: {}".format(payload["code"])
            raise MachineTranslationError(msg)

    def download_languages(self):
        """Download list of supported languages from a service."""
        response = self.request(
            "get",
            "https://translate.yandex.net/api/v1.5/tr.json/getLangs",
            params={"key": self.settings["key"], "ui": "en"},
        )
        payload = response.json()
        return payload["langs"].keys()

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
            "get",
            "https://translate.yandex.net/api/v1.5/tr.json/translate",
            params={
                "key": self.settings["key"],
                "text": text,
                "lang": f"{source_language}-{target_language}",
                "target": target_language,
            },
        )
        payload = response.json()

        for translation in payload["text"]:
            yield {
                "text": translation,
                "quality": self.max_score,
                "service": self.name,
                "source": text,
            }

    def get_error_message(self, exc):
        try:
            return exc.response.json()["message"]
        except Exception:
            return super().get_error_message(exc)
