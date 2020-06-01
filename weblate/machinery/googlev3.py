#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from weblate.machinery.base import MachineTranslation, MissingConfiguration


class GoogleV3Translation(MachineTranslation):
    """Google Translate API v3 machine translation support."""

    setup = None
    name = "Google Translate API v3"
    max_score = 90

    def __init__(self):
        """Check configuration."""
        super().__init__()
        if settings.MT_GOOGLE_CREDENTIALS is None or settings.MT_GOOGLE_PROJECT is None:
            raise MissingConfiguration("Google Translate requires API key and project")

        credentials = service_account.Credentials.from_service_account_file(
            settings.MT_GOOGLE_CREDENTIALS
        )

        self.client = TranslationServiceClient(credentials=credentials)
        self.parent = self.client.location_path(
            settings.MT_GOOGLE_PROJECT, settings.MT_GOOGLE_LOCATION
        )

    def download_languages(self):
        """List of supported languages."""
        return [
            language.language_code
            for language in self.client.get_supported_languages(self.parent).languages
        ]

    def download_translations(self, source, language, text, unit, user, search):
        """Download list of possible translations from a service."""
        trans = self.client.translate_text(
            [text], language, self.parent, source_language_code=source
        )

        yield {
            "text": trans.translations[0].translated_text,
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
