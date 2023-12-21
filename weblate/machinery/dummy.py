# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.machinery.base import MachineTranslation


class DummyTranslation(MachineTranslation):
    """Dummy machine translation for testing purposes."""

    name = "Dummy"

    def download_languages(self):
        """Dummy translation supports just Czech language."""
        return ("en", "cs")

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ):
        """Dummy translation supports just single phrase."""
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
