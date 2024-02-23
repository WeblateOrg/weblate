# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING, Literal

from django.core.cache import cache
from openai import OpenAI

from weblate.glossary.models import (
    get_glossary_terms,
    render_glossary_units_tsv,
)
from weblate.utils.errors import report_error

from .base import (
    BatchMachineTranslation,
    DownloadMultipleTranslations,
    MachineTranslationError,
)
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
{separator}
You treat strings like {placeable_1} or {placeable_2} as placeables for user input and keep them intact.
{glossary}
"""
SEPARATOR = "\n==WEBLATE_PART==\n"
SEPARATOR_PROMPT = f"""
You receive an input as strings separated by {SEPARATOR} and
your answer separates strings by {SEPARATOR}.
"""
GLOSSARY_PROMPT = """
Use the following glossary during the translation:
{}
"""


class OpenAITranslation(BatchMachineTranslation):
    name = "OpenAI"
    max_score = 90
    request_timeout = 60

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

    def format_prompt_part(self, name: Literal["style", "persona"]):
        text = self.settings[name]
        text = text.strip()
        if text and not text.endswith("."):
            text = f"{text}."
        return text

    def get_prompt(
        self, source_language: str, target_language: str, units: list
    ) -> str:
        glossary = ""
        if any(units):
            glossary = render_glossary_units_tsv(
                chain.from_iterable(get_glossary_terms(unit) for unit in units)
            )
            if glossary:
                glossary = GLOSSARY_PROMPT.format(glossary)
        separator = SEPARATOR_PROMPT if len(units) > 1 else ""
        return PROMPT.format(
            source_language=source_language,
            target_language=target_language,
            persona=self.format_prompt_part("persona"),
            style=self.format_prompt_part("style"),
            glossary=glossary,
            separator=separator,
            placeable_1=self.format_replacement(0, -1, "", None),
            placeable_2=self.format_replacement(123, -1, "", None),
        )

    def download_multiple_translations(
        self,
        source,
        language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = 75,
    ) -> DownloadMultipleTranslations:
        texts = [text for text, _unit in sources]
        units = [unit for _text, unit in sources]
        prompt = self.get_prompt(source, language, units)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": SEPARATOR.join(texts)},
        ]

        response = self.client.chat.completions.create(
            model=self.get_model(),
            messages=messages,
            temperature=0,
            frequency_penalty=0,
            presence_penalty=0,
        )

        result: DownloadMultipleTranslations = {}

        translations_string = response.choices[0].message.content
        if translations_string is None:
            report_error(
                cause="Blank assistant reply",
                extra_log=translations_string,
                message=True,
            )
            raise MachineTranslationError("Blank assistant reply")

        translations = translations_string.split(SEPARATOR)
        if len(translations) != len(texts):
            report_error(
                cause="Failed to parse assistant reply",
                extra_log=translations_string,
                message=True,
            )
            raise MachineTranslationError("Could not parse assistant reply")

        for index, text in enumerate(texts):
            # Extract the assistant's reply from the response
            try:
                translation = translations[index]
            except IndexError:
                report_error(cause="Missing assistant reply")
                continue

            result[text] = [
                {
                    "text": translation,
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                }
            ]
        return result
