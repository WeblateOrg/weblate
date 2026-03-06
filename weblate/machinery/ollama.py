# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Urtzi Odriozola <urtzi.odriozola@ni.eus>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

from urllib.parse import urljoin

from weblate.machinery.llm import BaseLLMTranslation
from weblate.utils.docs import VersionAdded

from .forms import OllamaMachineryForm


class OllamaTranslation(BaseLLMTranslation):
    """
    Ollama machine translation integration.

    Configurable machine translation interface that uses the
    Ollama language models.
    """

    name = "Ollama"
    end_point = "/api/chat"
    settings_form = OllamaMachineryForm
    doc_versions = (VersionAdded("5.15"),)

    def get_model(self) -> str:
        return self.settings["model"]

    def fetch_llm_translations(
        self, prompt: str, content: str, previous_content: str, previous_response: str
    ) -> str | None:
        payload = {
            "model": self.get_model(),
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": previous_content},
                {"role": "assistant", "content": previous_response},
                {"role": "user", "content": content},
            ],
            "stream": False,
        }
        api_url = urljoin(self.settings["base_url"], self.end_point)
        response = self.request("post", api_url, json=payload)

        if message := response.json().get("message"):
            return message["content"]

        return None
