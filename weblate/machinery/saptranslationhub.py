#
# Copyright ©  2018 Manuel Laggner <manuel.laggner@egger.com>
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
from requests.auth import _basic_auth_str

from .base import MachineTranslation
from .forms import SAPMachineryForm


class SAPTranslationHub(MachineTranslation):
    # https://api.sap.com/shell/discover/contentpackage/SAPTranslationHub/api/translationhub
    name = "SAP Translation Hub"
    settings_form = SAPMachineryForm

    @staticmethod
    def migrate_settings():
        return {
            "url": settings.MT_SAP_BASE_URL,
            "key": settings.MT_SAP_SANDBOX_APIKEY,
            "username": settings.MT_SAP_USERNAME,
            "password": settings.MT_SAP_PASSWORD,
            "enable_mt": bool(settings.MT_SAP_USE_MT),
        }

    def get_authentication(self):
        """Hook for backends to allow add authentication headers to request."""
        # to access the sandbox
        result = {}
        if self.settings["key"]:
            result["APIKey"] = self.settings["key"]

        # to access the productive API
        if self.settings["username"] and self.settings["password"]:
            result["Authorization"] = _basic_auth_str(
                self.settings["username"], self.settings["password"]
            )
        return result

    def download_languages(self):
        """Get all available languages from SAP Translation Hub."""
        # get all available languages
        response = self.request("get", self.settings["url"] + "languages")
        payload = response.json()

        return [d["id"] for d in payload["languages"]]

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
        # should the machine translation service be used?
        # (rather than only the term database)
        enable_mt = self.settings["enable_mt"]

        # build the json body
        data = {
            "targetLanguages": [language],
            "sourceLanguage": source,
            "enableMT": enable_mt,
            "enableTranslationQualityEstimation": enable_mt,
            "units": [{"value": text}],
        }

        # perform the request
        response = self.request("post", self.settings["url"] + "translate", json=data)
        payload = response.json()

        # prepare the translations for weblate
        for item in payload["units"]:
            for translation in item["translations"]:
                yield {
                    "text": translation["value"],
                    "quality": translation.get("qualityIndex", 100),
                    "service": self.name,
                    "source": text,
                }
