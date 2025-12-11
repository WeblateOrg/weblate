# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Urtzi Odriozola <urtzi.odriozola@ni.eus>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

from urllib.parse import urljoin

from weblate.machinery.llm import BaseLLMTranslation

from .forms import OllamaMachineryForm


class OllamaTranslation(BaseLLMTranslation):
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

    def fetch_llm_translations(self, prompt: str, content: str) -> str | None:
        payload = {
            "model": self.get_model(),
            "system": prompt,
            "prompt": content,
            "stream": False,
        }
        api_url = urljoin(self.settings["base_url"], self.end_point)
        response = self.request("post", api_url, json=payload)

        return response.json().get("response") or None
