#
# Copyright ©2018 Sun Zhigang <hzsunzhigang@corp.netease.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.conf import settings

from weblate.machinery.base import (
    MachineryRateLimit,
    MachineTranslation,
    MachineTranslationError,
    MissingConfiguration,
)

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
        "vi": "vie",
    }

    def __init__(self):
        """Check configuration."""
        super().__init__()
        if settings.MT_BAIDU_ID is None:
            raise MissingConfiguration("Baidu Translate requires app key")
        if settings.MT_BAIDU_SECRET is None:
            raise MissingConfiguration("Baidu Translate requires app secret")

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
            "vie",
        ]

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        search: bool,
        threshold: int = 75,
    ):
        """Download list of possible translations from a service."""
        salt, sign = self.signed_salt(
            settings.MT_BAIDU_ID, settings.MT_BAIDU_SECRET, text
        )
        args = {
            "q": text,
            "from": source,
            "to": language,
            "appid": settings.MT_BAIDU_ID,
            "salt": salt,
            "sign": sign,
        }

        response = self.request("get", BAIDU_API, params=args)
        payload = response.json()

        if "error_code" in payload:
            try:
                if int(payload["error_code"]) == 54003:
                    raise MachineryRateLimit(payload["error_msg"])
            except ValueError:
                pass
            raise MachineTranslationError(
                "Error {error_code}: {error_msg}".format(**payload)
            )

        for item in payload["trans_result"]:
            yield {
                "text": item["dst"],
                "quality": self.max_score,
                "service": self.name,
                "source": item["src"],
            }
