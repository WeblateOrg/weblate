#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

from weblate.machinery.base import MachineTranslation

from .forms import KeyURLMachineryForm

LIBRETRANSLATE_TRANSLATE = "{}translate"
LIBRETRANSLATE_LANGUAGES = "{}languages"


class LibreTranslateTranslation(MachineTranslation):
    """LibreTranslate machine translation support."""

    name = "LibreTranslate"
    max_score = 88
    language_map = {
        "zh_hans": "zh",
    }
    settings_form = KeyURLMachineryForm

    @staticmethod
    def migrate_settings():
        return {
            "url": settings.MT_LIBRETRANSLATE_API_URL,
            "key": settings.MT_LIBRETRANSLATE_KEY,
        }

    def download_languages(self):
        response = self.request(
            "get",
            LIBRETRANSLATE_LANGUAGES.format(self.settings["url"]),
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
            LIBRETRANSLATE_TRANSLATE.format(self.settings["url"]),
            data={
                "api_key": self.settings["key"],
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
