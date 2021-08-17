#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
# Copyright © 2021 Seth Falco <seth@falco.fun>
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

from weblate.machinery.base import MachineTranslation, MissingConfiguration

LIBRETRANSLATE_TRANSLATE = "{}translate"
LIBRETRANSLATE_LANGUAGES = "{}languages"


class LibreTranslateTranslation(MachineTranslation):
    """LibreTranslate machine translation support."""

    name = "LibreTranslate"
    max_score = 88
    language_map = {
        "zh_hans": "zh",
    }

    def __init__(self):
        """Check configuration."""
        super().__init__()
        if settings.MT_LIBRETRANSLATE_API_URL is None:
            raise MissingConfiguration("LibreTranslate requires API URL")

    def download_languages(self):
        response = self.request(
            "get",
            LIBRETRANSLATE_LANGUAGES.format(settings.MT_LIBRETRANSLATE_API_URL),
        )
        return [x["code"] for x in response.json()]

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
            "post",
            LIBRETRANSLATE_TRANSLATE.format(settings.MT_LIBRETRANSLATE_API_URL),
            data={
                "api_key": settings.MT_LIBRETRANSLATE_KEY,
                "q": text,
                "source": source,
                "target": language,
            },
        )
        payload = response.json()

        yield {
            "text": payload["translatedText"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
