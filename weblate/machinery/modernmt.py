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

import json

from django.conf import settings

import weblate.utils.version
from weblate.machinery.base import (
    MachineTranslation,
    MachineTranslationError,
    MissingConfiguration,
)


class ModernMTTranslation(MachineTranslation):
    """ModernMT machine translation support."""

    name = "ModernMT"
    max_score = 90

    def __init__(self):
        """Check configuration."""
        super().__init__()
        if settings.MT_MODERNMT_KEY is None:
            raise MissingConfiguration("ModernMT requires API key")

    def get_authentication(self):
        """Hook for backends to allow add authentication headers to request."""
        return {
            "MMT-ApiKey": settings.MT_MODERNMT_KEY,
            "MMT-Platform": "Weblate",
            "MMT-PlatformVersion": weblate.utils.version.VERSION,
        }

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        return (source, language) in self.supported_languages

    def download_languages(self):
        """List of supported languages."""
        response = self.request("get", settings.MT_MODERNMT_URL + "languages")
        payload = response.json()

        for source, targets in payload["data"].items():
            yield from ((source, target) for target in targets)

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
            settings.MT_MODERNMT_URL + "translate",
            params={"q": text, "source": source, "target": language},
        )
        payload = response.json()

        if "error" in payload:
            raise MachineTranslationError(payload["error"]["message"])

        yield {
            "text": payload["data"]["translation"],
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
