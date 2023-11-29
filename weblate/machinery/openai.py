# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.cache import cache
from openai import OpenAI

from .base import BatchMachineTranslation, MachineTranslationError
from .forms import OpenAIMachineryForm

if TYPE_CHECKING:
    from weblate.trans.models import Unit

PROMPT = """
You are a highly skilled translation assistant, adept at translating text
from language '{source_language}'
to language '{target_language}'
with precision and nuance.
{persona}
{style}
You always reply with translated string only.
You do not include transliteration.
{glossary}
"""


class OpenAITranslation(BatchMachineTranslation):
    name = "OpenAI"
    max_score = 90

    settings_form = OpenAIMachineryForm

    def __init__(self, settings=None):
        super().__init__(settings)
        self.client = OpenAI(api_key=self.settings["key"], timeout=self.request_timeout)
        self._models = None

    def is_supported(self, source, language):
        return True

    def get_model(self) -> str:
        if self._models is None:
            cache_key = self.get_cache_key("models")
            self._models = cache.get(cache_key)
            if self._models is None:
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

        raise MachineTranslationError(f"Unsupported model: {self.settings['model']}")

    def get_prompt(self, source_language: str, target_language: str) -> str:
        return PROMPT.format(
            source_language=source_language,
            target_language=target_language,
            persona=self.settings["persona"],
            style=self.settings["style"],
            glossary="",
        )

    def download_multiple_translations(
        self,
        source,
        language,
        sources: list[tuple[str, Unit]],
        user=None,
        threshold: int = 75,
    ) -> dict[str, list[dict[str, str]]]:
        texts = [text for text, _unit in sources]
        messages = [
            {"role": "system", "content": self.get_prompt(source, language)},
            *({"role": "user", "content": text} for text in texts),
        ]

        response = self.client.chat.completions.create(
            model=self.get_model(),
            messages=messages,
            temperature=0,
            max_tokens=1000,
            frequency_penalty=0,
            presence_penalty=0,
        )

        result = {}
        for index, text in enumerate(texts):
            # Extract the assistant's reply from the response
            assistant_reply = response.choices[index].message.content.strip()

            result[text] = [
                {
                    "text": assistant_reply,
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                }
            ]
        return result
