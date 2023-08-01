# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json

from django.conf import settings

import weblate.utils.version

from .base import MachineTranslation, MachineTranslationError
from .forms import ModernMTMachineryForm


class ModernMTTranslation(MachineTranslation):
    """ModernMT machine translation support."""

    name = "ModernMT"
    max_score = 90
    settings_form = ModernMTMachineryForm

    language_map = {
        "fa": "pes",
        "pt": "pt-PT",
        "sr": "sr-Cyrl",
        "zh_Hant": "zh-TW",
        "zh_Hans": "zh-CN",
    }

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").split("@")[0]

    @staticmethod
    def migrate_settings():
        return {
            "key": settings.MT_MODERNMT_KEY,
            "url": settings.MT_MODERNMT_URL,
        }

    def get_authentication(self):
        """Hook for backends to allow add authentication headers to request."""
        return {
            "MMT-ApiKey": self.settings["key"],
            "MMT-Platform": "Weblate",
            "MMT-PlatformVersion": weblate.utils.version.VERSION,
        }

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        return (source, language) in self.supported_languages

    def download_languages(self):
        """List of supported languages."""
        response = self.request("get", self.get_api_url("languages"))
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
        threshold: int = 75,
    ):
        """Download list of possible translations from a service."""
        response = self.request(
            "get",
            self.get_api_url("translate"),
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
            except json.JSONDecodeError:
                data = {}

            try:
                return data["error"]["message"]
            except KeyError:
                pass

        return super().get_error_message(exc)
