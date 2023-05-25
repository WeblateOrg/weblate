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
from requests.exceptions import HTTPError

from .base import MachineTranslation
from .forms import URLMachineryForm

AMAGAMA_LIVE = "https://amagama-live.translatehouse.org/api/v1"


class TMServerTranslation(MachineTranslation):
    """tmserver machine translation support."""

    name = "tmserver"
    settings_form = URLMachineryForm

    @staticmethod
    def migrate_settings():
        return {
            "url": settings.MT_TMSERVER,
        }

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("-", "_").lower()

    def download_languages(self):
        """Download list of supported languages from a service."""
        try:
            # This URL needs trailing slash, that's why blank string is included
            response = self.request("get", self.get_api_url("languages", ""))
            data = response.json()
        except HTTPError as error:
            if error.response.status_code == 404:
                return []
            raise
        return [
            (src, tgt)
            for src in data["sourceLanguages"]
            for tgt in data["targetLanguages"]
        ]

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        if not self.supported_languages:
            # Fallback for old tmserver which does not export list of
            # supported languages
            return True
        return (source, language) in self.supported_languages

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
        url = self.get_api_url(
            source, language, "unit", text[:500].replace("\r", " ").encode()
        )
        response = self.request("get", url)
        payload = response.json()

        for line in payload:
            yield {
                "text": line["target"],
                "quality": int(line["quality"]),
                "service": self.name,
                "source": line["source"],
            }


class AmagamaTranslation(TMServerTranslation):
    """Specific instance of tmserver ran by Virtaal authors."""

    name = "Amagama"
    settings_form = None

    @property
    def api_base_url(self):
        return AMAGAMA_LIVE
