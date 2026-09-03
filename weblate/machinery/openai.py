# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import ClassVar
from urllib.parse import quote

from django.core.cache import cache

from .base import (
    MachineryRateLimitError,
    MachineTranslationError,
)
from .forms import AzureOpenAIMachineryForm, MistralMachineryForm, OpenAIMachineryForm
from .llm import BaseLLMTranslation

MODEL_SAMPLE_LIMIT = 5
MODEL_ID_DISPLAY_LIMIT = 80


class BaseOpenAITranslation(BaseLLMTranslation):
    def get_runtime_base_url(self) -> str:
        raise NotImplementedError

    def get_chat_completions_url(self) -> str:
        raise NotImplementedError

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
            self.get_chat_completions_url(),
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
            self.get_chat_completions_url(),
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
        }

    @staticmethod
    def parse_chat_response(payload) -> str:
        if not isinstance(payload, dict):
            msg = "Invalid service response: expected a JSON object."
            raise MachineTranslationError(msg)

        choices = payload.get("choices")
        if not isinstance(choices, list):
            msg = 'Invalid service response: expected "choices" to be a list.'
            raise MachineTranslationError(msg)
        if not choices:
            msg = "Service response did not contain an assistant message."
            raise MachineTranslationError(msg)

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            msg = "Invalid service response: expected a choice object."
            raise MachineTranslationError(msg)
        message = first_choice.get("message")
        if not isinstance(message, dict):
            msg = 'Invalid service response: expected "message" to be an object.'
            raise MachineTranslationError(msg)
        content = message.get("content")
        if not isinstance(content, str):
            msg = "Assistant message did not contain text content."
            raise MachineTranslationError(msg)
        return content


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

    def get_custom_model(self) -> str | None:
        if self.settings["model"] != "custom":
            return None
        custom_model = self.settings.get("custom_model")
        if not isinstance(custom_model, str) or not custom_model:
            msg = "Custom model name is not configured."
            raise MachineTranslationError(msg)
        return custom_model

    def get_model(self) -> str:
        if custom_model := self.get_custom_model():
            return custom_model
        if self._models is None:
            cache_key = self.get_cache_key("models")
            models_cache = cache.get(cache_key)
            if models_cache is not None:
                # hiredis-py 3 makes list from set
                self._models = set(models_cache)
            else:
                response = self.request("get", self.get_models_url())
                payload = self.parse_json_response(response, "model listing response")
                self._models = self.parse_models(payload)
                cache.set(cache_key, self._models, 3600)

        return self.select_model()

    async def aget_model(self) -> str:
        if custom_model := self.get_custom_model():
            return custom_model
        if self._models is None:
            cache_key = self.get_cache_key("models")
            models_cache = await cache.aget(cache_key)
            if models_cache is not None:
                self._models = set(models_cache)
            else:
                response = await self.arequest("get", self.get_models_url())
                payload = self.parse_json_response(response, "model listing response")
                self._models = self.parse_models(payload)
                await cache.aset(cache_key, self._models, 3600)

        return self.select_model()

    @staticmethod
    def parse_models(payload) -> set[str]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            msg = (
                "Invalid model listing response: expected a JSON object containing "
                'a "data" list.'
            )
            raise MachineTranslationError(msg)

        data = payload["data"]
        models = {
            model["id"]
            for model in data
            if isinstance(model, dict)
            and isinstance(model.get("id"), str)
            and model["id"]
        }
        if data and not models:
            msg = (
                "Invalid model listing response: no valid model identifiers were found."
            )
            raise MachineTranslationError(msg)
        return models

    @staticmethod
    def format_model_id(model: str) -> str:
        if len(model) > MODEL_ID_DISPLAY_LIMIT:
            model = f"{model[: MODEL_ID_DISPLAY_LIMIT - 3]}..."
        return repr(model)

    @classmethod
    def format_model_sample(cls, models: set[str]) -> str:
        ordered_models = sorted(models)
        sample = ", ".join(
            cls.format_model_id(model) for model in ordered_models[:MODEL_SAMPLE_LIMIT]
        )
        omitted = len(ordered_models) - MODEL_SAMPLE_LIMIT
        if omitted > 0:
            return f"{sample}; {omitted} more not shown"
        return sample

    @staticmethod
    def format_model_count(models: set[str]) -> str:
        count = len(models)
        suffix = "" if count == 1 else "s"
        return f"{count} model identifier{suffix}"

    def select_model(self) -> str:
        if custom_model := self.get_custom_model():
            return custom_model

        models = self._models if self._models is not None else set()
        if not models:
            msg = (
                "The model listing endpoint returned no models. Check the API key "
                "permissions and API base URL, or configure a custom model."
            )
            raise MachineTranslationError(msg)

        if self.settings["model"] in models:
            return self.settings["model"]
        if self.settings["model"] == "auto":
            for model, _name in self.settings_form.MODEL_CHOICES:
                if model in {"auto", "custom"}:
                    continue
                if model in models:
                    return model

            msg = (
                "Automatic model selection failed: the service returned "
                f"{self.format_model_count(models)}, but none match the models "
                "available for automatic selection in Weblate. Returned models include: "
                f"{self.format_model_sample(models)}. Configure a custom model or "
                "update the models available to the service."
            )
            raise MachineTranslationError(msg)

        msg = (
            f"Configured model {self.format_model_id(self.settings['model'])} was not "
            "returned by the model listing endpoint. The service returned "
            f"{self.format_model_count(models)}, including: "
            f"{self.format_model_sample(models)}. Choose another model or configure "
            "it as a custom model."
        )
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

    async def aget_model(self) -> str:
        return self.get_model()
