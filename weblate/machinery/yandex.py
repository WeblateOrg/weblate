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

    def check_failure(self, response):
        if "code" not in response or response["code"] == 200:
            return
        if "message" in response:
            raise MachineTranslationError(response["message"])
        raise MachineTranslationError("Error: {}".format(response["code"]))

    def download_languages(self):
        """Download list of supported languages from a service."""
        response = self.request(
            "get",
            "https://translate.yandex.net/api/v1.5/tr.json/getLangs",
            params={"key": self.settings["key"], "ui": "en"},
        )
        payload = response.json()
        self.check_failure(payload)
        return payload["langs"].keys()

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
            "https://translate.yandex.net/api/v1.5/tr.json/translate",
            params={
                "key": self.settings["key"],
                "text": text,
                "lang": f"{source}-{language}",
                "target": language,
            },
        )
        payload = response.json()

        self.check_failure(payload)

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
