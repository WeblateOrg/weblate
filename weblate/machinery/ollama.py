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
    end_point = "/api/chat"
    settings_form = OllamaMachineryForm
    version_added = "5.15"

    def get_model(self) -> str:
        return self.settings["model"]

    def fetch_llm_translations(
        self, prompt: str, content: str, previous_content: str, previous_response: str
    ) -> str | None:
        model = self.get_traced_model()
        response = self.request(
            "post",
            self.get_chat_url(),
            json=self.get_chat_payload(
                model, prompt, content, previous_content, previous_response
            ),
        )
        return self.parse_chat_response(response.json())

    async def afetch_llm_translations(
        self, prompt: str, content: str, previous_content: str, previous_response: str
    ) -> str | None:
        model = await self.aget_traced_model()
        response = await self.arequest(
            "post",
            self.get_chat_url(),
            json=self.get_chat_payload(
                model, prompt, content, previous_content, previous_response
            ),
        )
        return self.parse_chat_response(response.json())

    @staticmethod
    def get_chat_payload(
        model: str,
        prompt: str,
        content: str,
        previous_content: str,
        previous_response: str,
    ) -> dict:
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": previous_content},
                {"role": "assistant", "content": previous_response},
                {"role": "user", "content": content},
            ],
            "stream": False,
        }

    def get_chat_url(self) -> str:
        return urljoin(self.settings["base_url"], self.end_point)

    @staticmethod
    def parse_chat_response(response_data) -> str | None:
        if message := response_data.get("message"):
            return message["content"]

        return None
