# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Sun Zhigang <hzsunzhigang@corp.netease.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from .base import DownloadTranslations, MachineTranslation, MachineTranslationError
from .forms import KeySecretMachineryForm

YOUDAO_API_ROOT = "https://openapi.youdao.com/api"


class YoudaoTranslation(MachineTranslation):
    """Youdao Zhiyun API machine translation support."""

    name = "Youdao Zhiyun"
    max_score = 90

    # Map codes used by Youdao to codes used by Weblate
    language_map = {"zh_Hans": "zh-CHS", "zh": "zh-CHS", "en": "EN"}
    settings_form = KeySecretMachineryForm

    def download_languages(self):
        """List of supported languages."""
        return [
            "zh-CHS",
            "ja",
            "EN",  # Officially youdao uses uppercase for en
            "ko",
            "fr",
            "ru",
            "pt",
            "es",
            "vi",
            "de",
            "ar",
            "id",
        ]

    def check_failure(self, response) -> None:
        super().check_failure(response)
        payload = response.json()
        if int(payload["errorCode"]) != 0:
            msg = "Error code: {}".format(payload["errorCode"])
            raise MachineTranslationError(msg)

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
        salt, sign = self.signed_salt(
            self.settings["key"], self.settings["secret"], text
        )

        response = self.request(
            "get",
            YOUDAO_API_ROOT,
            params={
                "q": text,
                "_from": source_language,
                "to": target_language,
                "appKey": self.settings["key"],
                "salt": salt,
                "sign": sign,
            },
        )
        payload = response.json()

        translation = payload["translation"][0]

        yield {
            "text": translation,
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
