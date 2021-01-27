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
from google.cloud.translate_v3 import TranslationServiceClient
from google.oauth2 import service_account

from weblate.machinery.base import MissingConfiguration
from weblate.machinery.google import GoogleBaseTranslation


class GoogleV3Translation(GoogleBaseTranslation):
    """Google Translate API v3 machine translation support."""

    setup = None
    name = "Google Translate API v3"
    max_score = 90

    def __init__(self):
        """Check configuration."""
        super().__init__()
        credentials = settings.MT_GOOGLE_CREDENTIALS
        project = settings.MT_GOOGLE_PROJECT
        location = settings.MT_GOOGLE_LOCATION

        if credentials is None or project is None:
            raise MissingConfiguration("Google Translate requires API key and project")

        credentials = service_account.Credentials.from_service_account_file(credentials)

        self.client = TranslationServiceClient(credentials=credentials)
        self.parent = f"projects/{project}/locations/{location}"

    def download_languages(self):
        """List of supported languages."""
        response = self.client.get_supported_languages(request={"parent": self.parent})
        return [language.language_code for language in response.languages]

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
        request = {
            "parent": self.parent,
            "contents": [text],
            "target_language_code": language,
            "source_language_code": source,
        }
        response = self.client.translate_text(request)

        yield {
            "text": response.translations[0].translated_text,
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
