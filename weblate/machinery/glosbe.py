# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.machinery.base import MachineTranslation


class GlosbeTranslation(MachineTranslation):
    """Glosbe machine translation support."""

    name = "Glosbe"
    max_score = 90
    do_cleanup = False

    def map_code_code(self, code):
        """Convert language to service specific code."""
        return code.replace("_", "-").split("-")[0].lower()

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

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
        params = {"from": source, "dest": language, "format": "json", "phrase": text}
        response = self.request(
            "get", "https://glosbe.com/gapi/translate", params=params
        )
        payload = response.json()

        if "tuc" not in payload:
            return

        for match in payload["tuc"]:
            if "phrase" not in match or match["phrase"] is None:
                continue
            yield {
                "text": match["phrase"]["text"],
                "quality": self.max_score,
                "service": self.name,
                "source": text,
            }
