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
    """Dummy glossary translation for testing purposes."""

    glossary_count_limit = 1

    def download_translations(
        self, source, language, text: str, unit, user, threshold: int = 75
    ) -> DownloadTranslations:
        """Translate with glossary."""
        self.get_glossary_id(source, language, unit)
        return super().download_translations(
            source, language, text, unit, user, threshold
        )

    def list_glossaries(self):
        """List glossaries."""
        return {}

    def delete_glossary(self, glossary_id: str) -> None:
        """Delete glossary."""
        return

    def delete_oldest_glossary(self) -> None:
        """Delete oldest glossary."""
        return self.delete_glossary("")

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ) -> None:
        """Create glossary."""
        return
