# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.cache import cache

from weblate.utils.errors import add_breadcrumb

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

    def fetch_llm_translations(self, prompt: str, content: str) -> str | None:
        from openai import RateLimitError
        from openai.types.chat import (
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
        )

        add_breadcrumb("openai", "prompt", prompt=prompt)
        add_breadcrumb("openai", "chat", content=content)

        messages: Iterable[
            ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam
        ] = [
            ChatCompletionSystemMessageParam(role="system", content=prompt),
            ChatCompletionUserMessageParam(
                role="user",
                content=content,
            ),
        ]

        try:
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

    settings_form = OpenAIMachineryForm

    def __init__(self, settings=None) -> None:
        from openai import OpenAI

        super().__init__(settings)
        self.client = OpenAI(
            api_key=self.settings["key"],
            timeout=self.request_timeout,
            base_url=self.settings.get("base_url") or None,
        )
        self._models: set[str] | None = None

    def get_model(self) -> str:
        if self._models is None:
            cache_key = self.get_cache_key("models")
            models_cache = cache.get(cache_key)
            if models_cache is not None:
                # hiredis-py 3 makes list from set
                self._models = set(models_cache)
            else:
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
    settings_form = AzureOpenAIMachineryForm

    def __init__(self, settings=None) -> None:
        from openai import AzureOpenAI

        super().__init__(settings)
        self.client = AzureOpenAI(
            api_key=self.settings["key"],
            api_version="2024-06-01",
            timeout=self.request_timeout,
            azure_endpoint=self.settings.get("azure_endpoint") or "",
            azure_deployment=self.settings["deployment"],
        )

    def get_model(self) -> str:
        return self.settings["deployment"]
