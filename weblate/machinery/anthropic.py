# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from urllib.parse import urljoin

from .base import MachineryRateLimitError
from .forms import AnthropicMachineryForm
from .llm import BaseLLMTranslation


class AnthropicTranslation(BaseLLMTranslation):
    """
    Anthropic Claude machine translation integration.

    Configurable machine translation interface that uses Anthropic's
    Claude language models.
    """

    name = "Anthropic"
    end_point = "/v1/messages"
    settings_form = AnthropicMachineryForm

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
            payload = response.json()
            error = payload.get("error", {})
            message = error.get("message", "Rate limit exceeded")
            raise MachineryRateLimitError(message)
        super().check_failure(response)

    def fetch_llm_translations(self, prompt: str, content: str) -> str | None:
        payload = {
            "model": self.get_model(),
            "max_tokens": self.settings.get("max_tokens", 4096),
            "system": prompt,
            "messages": [
                {"role": "user", "content": content},
            ],
        }
        api_url = urljoin(
            self.settings.get("base_url", "https://api.anthropic.com"), self.end_point
        )
        response = self.request("post", api_url, json=payload)
        response_data = response.json()

        content_blocks = response_data.get("content", [])
        if content_blocks and len(content_blocks) > 0:
            return content_blocks[0].get("text")
        return None
