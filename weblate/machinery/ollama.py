# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Urtzi Odriozola <urtzi.odriozola@ni.eus>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

from urllib.parse import urljoin

import requests

from weblate.machinery.base import (
    MachineTranslationError,
)
from weblate.machinery.llm import BaseLLMTranslation

from .forms import OllamaMachineryForm


class Ollama(BaseLLMTranslation):
    """
    Ollama machine translation integration.

    Configurable machine translation interface that uses the
    Ollama language models.
    """

    name = "Ollama"
    end_point = "/api/generate"
    settings_form = OllamaMachineryForm

    def get_model(self) -> str:
        return self.settings["model"]

    def _fetch_llm_translations(self, prompt: str, content: str) -> list[str]:
        try:
            payload = {
                "model": self.get_model(),
                "system": prompt,
                "prompt": content,
                "stream": False,
            }
            api_url = urljoin(self.settings["base_url"], self.end_point)
            response = requests.request(
                "post", api_url, json=payload, timeout=self.request_timeout
            )
        except Exception as error:
            raise MachineTranslationError(error) from error

        return response.json().get("response")
