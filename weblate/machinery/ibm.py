#
# Copyright ©2023 Kao, Ming-Yang <vincent0629@gmail.com>
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
from base64 import b64encode

from django.conf import settings

from weblate.machinery.base import MachineTranslation

from .forms import KeyURLMachineryForm


class IBMTranslation(MachineTranslation):
    """IBM Watson machine translation support."""

    name = "IBM"
    max_score = 88
    language_map = {
        "zh_Hant": "zh-TW",
        "zh_Hans": "zh",
    }
    settings_form = KeyURLMachineryForm

    @staticmethod
    def migrate_settings():
        return {
            "url": settings.MT_IBM_API_URL,
            "key": settings.MT_IBM_KEY,
        }

    def get_authentication(self):
        b64 = str(b64encode(f"apikey:{self.settings['key']}".encode()), "UTF-8")
        return {
            "Authorization": f"Basic {b64}",
            "Content-Type": "application/json",
        }

    def download_languages(self):
        response = self.request(
            "get",
            f"{self.api_base_url}/v3/languages?version=2018-05-01",
        )
        return [x["language"] for x in response.json()["languages"]]

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
        response = self.request(
            "post",
            f"{self.api_base_url}/v3/translate?version=2018-05-01",
            json={
                "text": [text],
                "source": source,
                "target": language,
            },
        )
        yield {
            "text": response.json()["translations"][0]["translation"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
