# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from .base import DownloadTranslations, MachineTranslation


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
