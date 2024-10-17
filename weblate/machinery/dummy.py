# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from .base import (
    DownloadTranslations,
    GlossaryMachineTranslationMixin,
    MachineTranslation,
)


class DummyTranslation(MachineTranslation):
    """Dummy machine translation for testing purposes."""

    name = "Dummy"

    def download_languages(self):
        """
        List supported languages.

        Dummy translation supports just Czech language.
        """
        return ("en", "cs")

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """
        Download translations.

        Dummy translation supports just few phrases.
        """
        if source == "en" and text.strip() == "Hello, world!":
            yield {
                "text": "Nazdar světe!",
                "quality": self.max_score,
                "service": "Dummy",
                "source": text,
            }
            yield {
                "text": "Ahoj světe!",
                "quality": self.max_score,
                "service": "Dummy",
                "source": text,
            }
        if source == "en" and text.strip() == "Hello, [X7X]!":
            yield {
                "text": "Nazdar [X7X ]!",
                "quality": self.max_score,
                "service": "Dummy",
                "source": text,
            }


class DummyGlossaryTranslation(DummyTranslation, GlossaryMachineTranslationMixin):
    def list_glossaries(self):
        return {"weblate:1:en:it:9e250d830c11d70f": "weblate:1:en:it:9e250d830c11d70f"}

    def delete_glossary(self, glossary_id: str) -> None:
        pass

    def delete_oldest_glossary(self) -> None:
        pass

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ) -> None:
        pass
