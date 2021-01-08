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

from urllib.parse import quote

from django.conf import settings
from requests.exceptions import HTTPError

from weblate.machinery.base import MachineTranslation, MissingConfiguration

AMAGAMA_LIVE = "https://amagama-live.translatehouse.org/api/v1"


class TMServerTranslation(MachineTranslation):
    """tmserver machine translation support."""

    name = "tmserver"

    def __init__(self):
        """Check configuration."""
        super().__init__()
        self.url = self.get_server_url()

    @staticmethod
    def get_server_url():
        """Return URL of a server."""
        if settings.MT_TMSERVER is None:
            raise MissingConfiguration("Not configured tmserver URL")

        return settings.MT_TMSERVER.rstrip("/")

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("-", "_").lower()

    def download_languages(self):
        """Download list of supported languages from a service."""
        try:
            # This will raise exception in DEBUG mode
            response = self.request("get", f"{self.url}/languages/")
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
        url = "{}/{}/{}/unit/{}".format(
            self.url,
            quote(source, b""),
            quote(language, b""),
            quote(text[:500].replace("\r", " ").encode(), b""),
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

    @staticmethod
    def get_server_url():
        return AMAGAMA_LIVE
