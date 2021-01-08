#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
    MachineTranslation,
    MachineTranslationError,
    MissingConfiguration,
)


class YandexTranslation(MachineTranslation):
    """Yandex machine translation support."""

    name = "Yandex"
    max_score = 90

    def __init__(self):
        """Check configuration."""
        super().__init__()
        if settings.MT_YANDEX_KEY is None:
            raise MissingConfiguration("Yandex Translate requires API key")

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
            params={"key": settings.MT_YANDEX_KEY, "ui": "en"},
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
        search: bool,
        threshold: int = 75,
    ):
        """Download list of possible translations from a service."""
        response = self.request(
            "get",
            "https://translate.yandex.net/api/v1.5/tr.json/translate",
            params={
                "key": settings.MT_YANDEX_KEY,
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
