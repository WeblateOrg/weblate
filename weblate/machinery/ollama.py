# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Urtzi Odriozola <urtzi.odriozola@ni.eus>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

from urllib.parse import urljoin

from weblate.machinery.base import MachineTranslationError
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
        return self.parse_chat_response(self.parse_json_response(response))

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
        return self.parse_chat_response(self.parse_json_response(response))

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
    def parse_chat_response(response_data) -> str:
        if not isinstance(response_data, dict):
            msg = "Invalid service response: expected a JSON object."
            raise MachineTranslationError(msg)
        if "message" not in response_data:
            msg = "Service response did not contain an assistant message."
            raise MachineTranslationError(msg)

        message = response_data["message"]
        if not isinstance(message, dict):
            msg = 'Invalid service response: expected "message" to be an object.'
            raise MachineTranslationError(msg)
        content = message.get("content")
        if not isinstance(content, str):
            msg = "Assistant message did not contain text content."
            raise MachineTranslationError(msg)
        return content
