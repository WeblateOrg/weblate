# Copyright © AlexEbenrode <alexebenrode@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from urllib.parse import unquote_plus

from .base import DownloadTranslations, MachineTranslation, MachineTranslationError
from .forms import KeyMachineryForm


class YandexV2Translation(MachineTranslation):
    """Yandex machine translation support."""

    name = "Yandex v2"
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
        key = self.settings["key"]
        response = self.request(
            "post",
            "https://translate.api.cloud.yandex.net/translate/v2/languages",
            headers={"Authorization": f"Api-Key {key}"},
        )
        payload = response.json()

        return [x["code"] for x in payload["languages"]]

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
        key = self.settings["key"]
        response = self.request(
            "post",
            "https://translate.api.cloud.yandex.net/translate/v2/translate",
            params={
                "texts": text,
                "sourceLanguageCode": source_language,
                "targetLanguageCode": target_language,
            },
            headers={"Authorization": f"Api-Key {key}"},
        )
        payload = json.loads(unquote_plus(response.text))

        for translation in payload["translations"]:
            yield {
                "text": translation["text"],
                "quality": self.max_score,
                "service": self.name,
                "source": text,
            }

    def get_error_message(self, exc):
        try:
            return exc.response.json()["message"]
        except Exception:
            return super().get_error_message(exc)
