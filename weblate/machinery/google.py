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


import json

from django.conf import settings

from google.cloud.translate_v3 import TranslationServiceClient
from google.oauth2 import service_account
from weblate.machinery.base import (
    MachineTranslation,
    MachineTranslationError,
    MissingConfiguration,
)

GOOGLE_API_ROOT = "https://translation.googleapis.com/language/translate/v2/"


class GoogleTranslation(MachineTranslation):
    """Google Translate API v2 machine translation support."""

    name = "Google Translate"
    max_score = 90

    # Map old codes used by Google to new ones used by Weblate
    language_map = {"he": "iw", "jv": "jw", "nb": "no", "fil": "tl"}

    def __init__(self):
        """Check configuration."""
        super().__init__()
        if settings.MT_GOOGLE_KEY is None:
            raise MissingConfiguration("Google Translate requires API key")

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").split("@")[0]

    def download_languages(self):
        """List of supported languages."""
        response = self.request(
            "get", GOOGLE_API_ROOT + "languages", params={"key": settings.MT_GOOGLE_KEY}
        )
        payload = response.json()

        if "error" in payload:
            raise MachineTranslationError(payload["error"]["message"])

        return [d["language"] for d in payload["data"]["languages"]]

    def download_translations(self, source, language, text, unit, user, search):
        """Download list of possible translations from a service."""
        response = self.request(
            "get",
            GOOGLE_API_ROOT,
            params={
                "key": settings.MT_GOOGLE_KEY,
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
        if hasattr(exc, "read"):
            content = exc.read()
            try:
                data = json.loads(content)
                return data["error"]["message"]
            except Exception:
                pass

        return super().get_error_message(exc)


class GoogleTranslationV3(MachineTranslation):
    """Google Translate API v3 machine translation support."""

    setup = None
    name = "Google Translate API v3"
    max_score = 90

    def __init__(self):
        """Check configuration."""
        super().__init__()
        config_error = []
        if settings.MT_GOOGLE_CREDENTIALS is None:
            config_error.append("Google Translate requires API key")
        if settings.MT_GOOGLE_PROJECT is None:
            config_error.append(
                "You have to specify Google Cloud project "
                "affiliated with provided credentials"
            )
        if len(config_error) > 0:
            raise MachineTranslationError(", ".join(config_error))

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
            l.language_code
            for l in self.client.get_supported_languages(self.parent).languages
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
