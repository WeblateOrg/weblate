"""
Machine translation example.

This example uses fictional http://example.com/ service to translate the
strings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.machinery.base import MachineTranslation

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.machinery.base import DownloadTranslations
    from weblate.trans.models import Unit


class SampleTranslation(MachineTranslation):
    """Sample machine translation interface."""

    name = "Sample"

    def download_languages(self):
        """Return list of languages your machine translation supports."""
        response = self.request("get", "http://example.com/languages")
        return response.json()["languages"]

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit: Unit | None,
        user: User | None,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Return tuple with translations."""
        response = self.request(
            "get",
            "http://example.com/translate",
            params={
                "source_language": source_language,
                "target_language": target_language,
                "text": text,
            },
        )

        for translation in response.json()["translations"]:
            yield {
                "text": translation,
                "quality": 100,
                "service": self.name,
                "source": text,
            }
