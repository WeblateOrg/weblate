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

from weblate.machinery.base import MachineTranslation, MissingConfiguration


class SAPTranslationHub(MachineTranslation):
    # https://api.sap.com/shell/discover/contentpackage/SAPTranslationHub/api/translationhub
    name = "SAP Translation Hub"

    def __init__(self):
        """Check configuration."""
        super().__init__()
        if settings.MT_SAP_BASE_URL is None:
            raise MissingConfiguration("missing SAP Translation Hub configuration")

    def get_authentication(self):
        """Hook for backends to allow add authentication headers to request."""
        # to access the sandbox
        result = {}
        if settings.MT_SAP_SANDBOX_APIKEY:
            result["APIKey"] = settings.MT_SAP_SANDBOX_APIKEY

        # to access the productive API
        if settings.MT_SAP_USERNAME and settings.MT_SAP_PASSWORD:
            result["Authorization"] = _basic_auth_str(
                settings.MT_SAP_USERNAME, settings.MT_SAP_PASSWORD
            )
        return result

    def download_languages(self):
        """Get all available languages from SAP Translation Hub."""
        # get all available languages
        response = self.request("get", settings.MT_SAP_BASE_URL + "languages")
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
        enable_mt = bool(settings.MT_SAP_USE_MT)

        # build the json body
        data = {
            "targetLanguages": [language],
            "sourceLanguage": source,
            "enableMT": enable_mt,
            "enableTranslationQualityEstimation": enable_mt,
            "units": [{"value": text}],
        }

        # perform the request
        response = self.request(
            "post", settings.MT_SAP_BASE_URL + "translate", json=data
        )
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
