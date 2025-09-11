"""Machine translation example."""

from __future__ import annotations

from typing import TYPE_CHECKING

import dictionary  # type: ignore[import-not-found]

from weblate.machinery.base import MachineTranslation

if TYPE_CHECKING:
    from weblate.machinery.base import DownloadTranslations


class SampleTranslation(MachineTranslation):
    """Sample machine translation interface."""

    name = "Sample"

    def download_languages(self):
        """Return list of languages your machine translation supports."""
        return {"cs"}

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Return tuple with translations."""
        for t in dictionary.translate(text):
            yield {"text": t, "quality": 100, "service": self.name, "source": text}
