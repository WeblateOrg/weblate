# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Sun Zhigang <hzsunzhigang@corp.netease.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from .base import (
    DownloadTranslations,
    MachineryRateLimitError,
    MachineTranslation,
    MachineTranslationError,
)
from .forms import KeySecretMachineryForm

BAIDU_API = "http://api.fanyi.baidu.com/api/trans/vip/translate"


class BaiduTranslation(MachineTranslation):
    """Baidu API machine translation support."""

    name = "Baidu"
    max_score = 90

    # Map codes used by Baidu to codes used by Weblate
    language_map = {
        "zh_Hans": "zh",
        "ja": "jp",
        "ko": "kor",
        "fr": "fra",
        "es": "spa",
        "ar": "ara",
        "bg": "bul",
        "et": "est",
        "da": "dan",
        "fi": "fin",
        "ro": "rom",
        # The slo should map to Slovak, but Baidu uses this code for Slovenian
        "sl": "slo",
        "sw": "swe",
        "zh_Hant": "cht",
        "vi": "vie",  # codespell:ignore vie
    }
    settings_form = KeySecretMachineryForm

    def download_languages(self):
        """List of supported languages."""
        return [
            "zh",
            "en",
            "yue",
            "wyw",
            "jp",
            "kor",
            "fra",
            "spa",
            "th",
            "ara",
            "ru",
            "pt",
            "de",
            "it",
            "el",
            "nl",
            "pl",
            "bul",
            "est",
            "dan",
            "fin",
            "cs",
            "rom",
            "slo",
            "swe",
            "hu",
            "cht",
            "vie",  # codespell:ignore vie
        ]

    def check_failure(self, response) -> None:
        payload = response.json()

        if "error_code" in payload:
            try:
                error_code = int(payload["error_code"])
            except ValueError:
                pass
            else:
                if error_code == 54003:
                    raise MachineryRateLimitError(payload["error_msg"])
            msg = "Error {error_code}: {error_msg}".format(**payload)
            raise MachineTranslationError(msg)
        super().check_failure(response)

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
        args = {
            "q": text,
            "from": source_language,
            "to": target_language,
            "appid": self.settings["key"],
            "salt": salt,
            "sign": sign,
        }

        response = self.request("get", BAIDU_API, params=args)
        payload = response.json()

        for item in payload["trans_result"]:
            yield {
                "text": item["dst"],
                "quality": self.max_score,
                "service": self.name,
                "source": item["src"],
            }
