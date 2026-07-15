# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import ClassVar
from urllib.parse import quote, urljoin

from django.core.cache import cache

from .base import (
    MachineryRateLimitError,
    MachineTranslationError,
)
from .forms import AzureOpenAIMachineryForm, MistralMachineryForm, OpenAIMachineryForm
from .llm import BaseLLMTranslation


class BaseOpenAITranslation(BaseLLMTranslation):
    def get_runtime_base_url(self) -> str:
        raise NotImplementedError

    def get_chat_completions_url(self) -> str:
        raise NotImplementedError

    @staticmethod
    def join_api_url(base_url: str, path: str) -> str:
        return urljoin(f"{base_url.rstrip('/')}/", path)

    def check_failure(self, response) -> None:
        if response.status_code == 429:
            message = self.get_error_detail(response) or "Rate limit exceeded"
            raise MachineryRateLimitError(message)
        super().check_failure(response)

    def fetch_llm_translations(
        self, prompt: str, content: str, previous_content: str, previous_response: str
    ) -> str | None:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": previous_content},
            {"role": "assistant", "content": previous_response},
            {"role": "user", "content": content},
        ]
        self.validate_runtime_url(self.get_runtime_base_url())
        model = self.get_traced_model()
        response = self.request(
            "post",
            self.get_chat_completions_url(),
            json={
                "model": model,
                "messages": messages,
            },
        )
        payload = response.json()
        choices = payload.get("choices", []) if isinstance(payload, dict) else []
        if choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message", {})
                if isinstance(message, dict):
                    return message.get("content")
        return None


class OpenAITranslation(BaseOpenAITranslation):
    name = "OpenAI"
    trusted_error_hosts: ClassVar[set[str]] = {"api.openai.com"}

    version_added = "5.3"

    settings_form: type[OpenAIMachineryForm | MistralMachineryForm] = (
        OpenAIMachineryForm
    )

    def __init__(self, settings=None) -> None:
        super().__init__(settings)
        self._models: set[str] | None = None

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings['key']}"}

    def get_runtime_base_url(self) -> str:
        return self.settings.get("base_url") or "https://api.openai.com/v1"

    def get_models_url(self) -> str:
        return self.join_api_url(self.get_runtime_base_url(), "models")

    def get_chat_completions_url(self) -> str:
        return self.join_api_url(self.get_runtime_base_url(), "chat/completions")

    def get_model(self) -> str:
        if self._models is None:
            cache_key = self.get_cache_key("models")
            models_cache = cache.get(cache_key)
            if models_cache is not None:
                # hiredis-py 3 makes list from set
                self._models = set(models_cache)
            else:
                self.validate_runtime_url(self.get_runtime_base_url())
                payload = self.request("get", self.get_models_url()).json()
                models = payload.get("data", []) if isinstance(payload, dict) else []
                self._models = {
                    model["id"]
                    for model in models
                    if isinstance(model, dict) and isinstance(model.get("id"), str)
                }
                cache.set(cache_key, self._models, 3600)

        if self.settings["model"] in self._models:
            return self.settings["model"]
        if self.settings["model"] == "auto":
            for model, _name in self.settings_form.MODEL_CHOICES:
                if model == "auto":
                    continue
                if model in self._models:
                    return model
        if self.settings["model"] == "custom":
            return self.settings["custom_model"]

        msg = f"Unsupported model: {self.settings['model']}"
        raise MachineTranslationError(msg)


class AzureOpenAITranslation(BaseOpenAITranslation):
    name = "Azure OpenAI"
    version_added = "5.8"
    settings_form = AzureOpenAIMachineryForm

    api_version = "2024-06-01"

    def get_headers(self) -> dict[str, str]:
        return {"api-key": self.settings["key"]}

    def get_runtime_base_url(self) -> str:
        return self.settings.get("azure_endpoint") or ""

    def get_chat_completions_url(self) -> str:
        deployment = quote(self.settings["deployment"], safe="")
        return self.join_api_url(
            self.get_runtime_base_url(),
            f"openai/deployments/{deployment}/chat/completions"
            f"?api-version={self.api_version}",
        )

    def get_model(self) -> str:
        return self.settings["deployment"]
