# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Seth Falco <seth@falco.fun>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BatchMachineTranslation, DownloadMultipleTranslations
from .forms import LibreTranslateMachineryForm

if TYPE_CHECKING:
    from weblate.trans.models import Unit


class LibreTranslateTranslation(BatchMachineTranslation):
    """LibreTranslate machine translation support."""

    name = "LibreTranslate"
    max_score = 89
    language_map = {
        "zh_Hans": "zh",
    }
    settings_form = LibreTranslateMachineryForm
    request_timeout = 20

    def download_languages(self):
        response = self.request(
            "get",
            self.get_api_url("languages"),
        )
        return [x["code"] for x in response.json()]

    def download_multiple_translations(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = 75,
    ) -> DownloadMultipleTranslations:
        """Download list of possible translations from a service."""
        texts = [text for text, _unit in sources]
        response = self.request(
            "post",
            self.get_api_url("translate"),
            json={
                "api_key": self.settings["key"],
                "q": texts,
                "source": source_language,
                "target": target_language,
            },
        )
        payload = response.json()
        translated_texts = payload["translatedText"]

        return {
            text: [
                {
                    "text": translated_texts[index],
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                }
            ]
            for index, text in enumerate(texts)
        }
