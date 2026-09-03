# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import ClassVar

from .base import MachineryRateLimitError, MachineTranslationError
from .forms import AnthropicMachineryForm
from .llm import BaseLLMTranslation


class AnthropicTranslation(BaseLLMTranslation):
    """
    Anthropic Claude machine translation integration.

    Configurable machine translation interface that uses Anthropic's
    Claude language models.
    """

    name = "Anthropic"
    trusted_error_hosts: ClassVar[set[str]] = {"api.anthropic.com"}
    end_point = "v1/messages"
    settings_form = AnthropicMachineryForm
    version_added = "5.16"

    def get_model(self) -> str:
        if self.settings["model"] == "custom":
            return self.settings["custom_model"]
        return self.settings["model"]

    def get_headers(self) -> dict[str, str]:
        """Add Anthropic-specific authentication headers."""
        return {
            "x-api-key": self.settings["key"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def check_failure(self, response) -> None:
        if response.status_code == 429:
            message = self.get_error_detail(response) or "Rate limit exceeded"
            raise MachineryRateLimitError(message)
        super().check_failure(response)

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

    def get_chat_payload(
        self,
        model: str,
        prompt: str,
        content: str,
        previous_content: str,
        previous_response: str,
    ) -> dict:
        return {
            "model": model,
            "max_tokens": self.settings.get("max_tokens", 4096),
            "system": prompt,
            "messages": [
                {"role": "user", "content": previous_content},
                {"role": "assistant", "content": previous_response},
                {"role": "user", "content": content},
            ],
        }

    def get_chat_url(self) -> str:
        base_url = (
            self.settings.get("base_url") or "https://api.anthropic.com"
        ).rstrip("/")
        # The endpoint carries the API version, so strip it from the base URL
        # to accept configurations which spell it out there as well.
        version = self.end_point.partition("/")[0]
        if base_url.endswith(f"/{version}"):
            base_url = base_url[: -len(version) - 1]
        return self.join_api_url(base_url, self.end_point)

    @staticmethod
    def parse_chat_response(response_data) -> str:
        if not isinstance(response_data, dict):
            msg = "Invalid service response: expected a JSON object."
            raise MachineTranslationError(msg)

        content_blocks = response_data.get("content")
        if not isinstance(content_blocks, list):
            msg = 'Invalid service response: expected "content" to be a list.'
            raise MachineTranslationError(msg)
        if not content_blocks:
            msg = "Service response did not contain an assistant message."
            raise MachineTranslationError(msg)

        invalid_block = False
        for block in content_blocks:
            if not isinstance(block, dict):
                invalid_block = True
            elif block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    return text
                msg = "Assistant message did not contain text content."
                raise MachineTranslationError(msg)

        if invalid_block:
            msg = "Invalid service response: expected content blocks to be objects."
            raise MachineTranslationError(msg)
        msg = "Assistant message did not contain text content."
        raise MachineTranslationError(msg)
