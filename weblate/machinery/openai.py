# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.core.cache import cache

from .base import (
    MachineryRateLimitError,
    MachineTranslationError,
)
from .forms import AzureOpenAIMachineryForm, OpenAIMachineryForm
from .llm import BaseLLMTranslation

if TYPE_CHECKING:
    from collections.abc import Iterable

    from openai import OpenAI


class BaseOpenAITranslation(BaseLLMTranslation):
    client: OpenAI

    def get_runtime_base_url(self) -> str:
        raise NotImplementedError

    def fetch_llm_translations(
        self, prompt: str, content: str, previous_content: str, previous_response: str
    ) -> str | None:
        from openai import RateLimitError  # noqa: PLC0415
        from openai.types.chat import (  # noqa: PLC0415
            ChatCompletionAssistantMessageParam,
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
        )

        messages: Iterable[
            ChatCompletionSystemMessageParam
            | ChatCompletionUserMessageParam
            | ChatCompletionAssistantMessageParam
        ] = [
            ChatCompletionSystemMessageParam(role="system", content=prompt),
            ChatCompletionUserMessageParam(
                role="user",
                content=previous_content,
            ),
            ChatCompletionAssistantMessageParam(
                role="assistant",
                content=previous_response,
            ),
            ChatCompletionUserMessageParam(
                role="user",
                content=content,
            ),
        ]
        try:
            self.validate_runtime_url(self.get_runtime_base_url())
            response = self.client.chat.completions.create(
                model=self.get_model(),
                messages=messages,
            )
        except RateLimitError as error:
            if not isinstance(error.body, dict) or not (
                message := error.body.get("message")
            ):
                message = error.message
            raise MachineryRateLimitError(message) from error

        return response.choices[0].message.content


class OpenAITranslation(BaseOpenAITranslation):
    name = "OpenAI"
    trusted_error_hosts: ClassVar[set[str]] = {"api.openai.com"}

    version_added = "5.3"

    settings_form = OpenAIMachineryForm

    def __init__(self, settings=None) -> None:
        from openai import OpenAI  # noqa: PLC0415

        super().__init__(settings)
        self.client = OpenAI(
            api_key=self.settings["key"],
            timeout=self.request_timeout,
            base_url=self.settings.get("base_url") or None,
        )
        self._models: set[str] | None = None

    def get_runtime_base_url(self) -> str:
        return self.settings.get("base_url") or "https://api.openai.com/v1"

    def get_model(self) -> str:
        if self._models is None:
            cache_key = self.get_cache_key("models")
            models_cache = cache.get(cache_key)
            if models_cache is not None:
                # hiredis-py 3 makes list from set
                self._models = set(models_cache)
            else:
                self.validate_runtime_url(self.get_runtime_base_url())
                self._models = {model.id for model in self.client.models.list()}
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

    def __init__(self, settings=None) -> None:
        from openai import AzureOpenAI  # noqa: PLC0415

        super().__init__(settings)
        self.client = AzureOpenAI(
            api_key=self.settings["key"],
            api_version="2024-06-01",
            timeout=self.request_timeout,
            azure_endpoint=self.settings.get("azure_endpoint") or "",
            azure_deployment=self.settings["deployment"],
        )

    def get_runtime_base_url(self) -> str:
        return self.settings.get("azure_endpoint") or ""

    def get_model(self) -> str:
        return self.settings["deployment"]
