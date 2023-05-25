#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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
from requests.exceptions import RequestException

from .base import MachineTranslation, MachineTranslationError
from .forms import KeyMachineryForm

GOOGLE_API_ROOT = "https://translation.googleapis.com/language/translate/v2/"


class GoogleBaseTranslation(MachineTranslation):
    # Map codes used by Google to the ones used by Weblate
    language_map = {
        "nb_NO": "no",
        "fil": "tl",
        "zh_Hant": "zh-TW",
        "zh_Hans": "zh-CN",
    }

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").split("@")[0]


class GoogleTranslation(GoogleBaseTranslation):
    """Google Translate API v2 machine translation support."""

    name = "Google Translate"
    max_score = 90
    settings_form = KeyMachineryForm

    @staticmethod
    def migrate_settings():
        return {
            "key": settings.MT_GOOGLE_KEY,
        }

    def download_languages(self):
        """List of supported languages."""
        response = self.request(
            "get", GOOGLE_API_ROOT + "languages", params={"key": self.settings["key"]}
        )
        payload = response.json()

        if "error" in payload:
            raise MachineTranslationError(payload["error"]["message"])

        return [d["language"] for d in payload["data"]["languages"]]

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

        if "error" in payload:
            raise MachineTranslationError(payload["error"]["message"])

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
