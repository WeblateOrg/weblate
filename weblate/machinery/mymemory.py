# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings

from .base import MachineTranslation
from .forms import MyMemoryMachineryForm


class MyMemoryTranslation(MachineTranslation):
    """MyMemory machine translation support."""

    name = "MyMemory"
    do_cleanup = False
    settings_form = MyMemoryMachineryForm

    @staticmethod
    def migrate_settings():
        return {
            "email": settings.MT_MYMEMORY_EMAIL,
            "username": settings.MT_MYMEMORY_USER,
            "key": settings.MT_MYMEMORY_KEY,
        }

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-")

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        return (
            self.lang_supported(source)
            and self.lang_supported(language)
            and source != language
        )

    @staticmethod
    def lang_supported(language):
        """Almost any language without modifiers is supported."""
        if language in ("ia", "tt", "ug"):
            return False
        return "@" not in language

    def format_match(self, match):
        """Reformat match to (translation, quality) tuple."""
        result = {
            "text": match["translation"],
            "quality": int(100 * match["match"]),
            "service": self.name,
            "source": match["segment"],
        }

        if match["last-updated-by"]:
            result["origin"] = match["last-updated-by"]

        if match["reference"]:
            result["origin_detail"] = match["reference"]

        return result

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ):
        """Download list of possible translations from MyMemory."""
        args = {
            "q": text.split(". ")[0][:500],
            "langpair": f"{source}|{language}",
        }
        if self.settings["email"]:
            args["de"] = self.settings["email"]
        if self.settings["username"]:
            args["user"] = self.settings["username"]
        if self.settings["key"]:
            args["key"] = self.settings["key"]

        response = self.request_status(
            "get", "https://mymemory.translated.net/api/get", params=args
        )
        for match in response["matches"]:
            result = self.format_match(match)
            if result["quality"] > threshold:
                yield result
