# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import defaultdict
from itertools import chain
from typing import TYPE_CHECKING, Literal, overload

from django.core.cache import cache

from weblate.glossary.models import (
    fetch_glossary_terms,
    get_glossary_terms,
    render_glossary_units_tsv,
)
from weblate.utils.errors import add_breadcrumb

from .base import (
    BatchMachineTranslation,
    DownloadMultipleTranslations,
    MachineryRateLimitError,
    MachineTranslationError,
)
from .forms import AzureOpenAIMachineryForm, OpenAIMachineryForm

if TYPE_CHECKING:
    from openai import OpenAI

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
{placeables}
{glossary}
"""
SEPARATOR = "\n==WEBLATE_PART==\n"
SEPARATOR_RE = re.compile(r"\n *==WEBLATE_PART== *\n")
SEPARATOR_PROMPT = f"""
You receive an input as strings separated by {SEPARATOR} and
your answer separates strings by {SEPARATOR}.
"""
REPHRASE_PROMPT = f"""
You receive an input as the source and existing translation strings separated
by {SEPARATOR} and you answer three rephrased translation strings separated by
{SEPARATOR}.
"""
GLOSSARY_PROMPT = """
Use the following glossary during the translation:
{}
"""
PLACEABLES_PROMPT = """
You treat strings like {placeable_1} or {placeable_2} as placeables for user input and keep them intact.
"""


class BaseOpenAITranslation(BatchMachineTranslation):
    max_score = 90
    request_timeout = 60
    client: OpenAI

    def __init__(self, settings=None) -> None:
        super().__init__(settings)

    def is_supported(self, source_language, target_language) -> bool:
        return True

    def format_prompt_part(self, name: Literal["style", "persona"]):
        text = self.settings[name]
        text = text.strip()
        if text and not text.endswith("."):
            text = f"{text}."
        return text

    def _get_prompt(
        self,
        source_language: str,
        target_language: str,
        texts: list[str],
        units: list[Unit | None],
        *,
        rephrase: bool = False,
    ) -> str:
        glossary = ""

        if any(units):
            fetch_glossary_terms([unit for unit in units if unit is not None])
            glossary = render_glossary_units_tsv(
                chain.from_iterable(
                    get_glossary_terms(unit, include_variants=False)
                    for unit in units
                    if unit is not None
                )
            )
            if glossary:
                glossary = GLOSSARY_PROMPT.format(glossary)

        separator = ""
        if rephrase:
            separator = REPHRASE_PROMPT
        elif len(units) > 1:
            separator = SEPARATOR_PROMPT

        placeables = ""
        if any(self.replacement_start in text for text in texts):
            placeables = PLACEABLES_PROMPT.format(
                placeable_1=self.format_replacement(0, -1, "", None),
                placeable_2=self.format_replacement(123, -1, "", None),
            )

        return PROMPT.format(
            source_language=source_language,
            target_language=target_language,
            persona=self.format_prompt_part("persona"),
            style=self.format_prompt_part("style"),
            glossary=glossary,
            separator=separator,
            placeables=placeables,
        )

    def download_multiple_translations(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = 75,
    ) -> DownloadMultipleTranslations:
        rephrase: list[tuple[str, Unit]] = []
        texts: list[str] = []
        units: list[Unit | None] = []

        # Separate rephrasing and new translations
        for text, unit in sources:
            if unit is not None and unit.translated and not unit.readonly:
                rephrase.append((text, unit))
            else:
                texts.append(text)
                units.append(unit)

        # Collect results
        result: DownloadMultipleTranslations = defaultdict(list)

        # Fetch rephrasing each string separately
        if rephrase:
            for text, unit in rephrase:
                self._download(
                    result,
                    source_language,
                    target_language,
                    [text],
                    [unit],
                    rephrase=True,
                )

        # Fetch translations in batch
        if texts:
            self._download(result, source_language, target_language, texts, units)

        return result

    @overload
    def _download(
        self,
        result: DownloadMultipleTranslations,
        source_language,
        target_language,
        texts: list[str],
        units: list[Unit],
        *,
        rephrase: Literal[True],
    ): ...
    @overload
    def _download(
        self,
        result: DownloadMultipleTranslations,
        source_language,
        target_language,
        texts: list[str],
        units: list[Unit | None],
    ): ...
    def _download(
        self,
        result: DownloadMultipleTranslations,
        source_language,
        target_language,
        texts,
        units,
        *,
        rephrase=False,
    ):
        from openai import RateLimitError
        from openai.types.chat import (
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
        )

        prompt = self._get_prompt(
            source_language, target_language, texts, units, rephrase=rephrase
        )
        content = SEPARATOR.join(texts if not rephrase else [*texts, units[0].target])
        add_breadcrumb("openai", "prompt", prompt=prompt)
        add_breadcrumb("openai", "chat", content=content)

        messages = [
            ChatCompletionSystemMessageParam(role="system", content=prompt),
            ChatCompletionUserMessageParam(
                role="user",
                content=content,
            ),
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.get_model(),
                messages=messages,  # type: ignore[arg-type]
                temperature=0,
                frequency_penalty=0,
                presence_penalty=0,
            )
        except RateLimitError as error:
            if not isinstance(error.body, dict) or not (
                message := error.body.get("message")
            ):
                message = error.message
            raise MachineryRateLimitError(message) from error

        translations_string = response.choices[0].message.content
        add_breadcrumb("openai", "response", translations_string=translations_string)
        if translations_string is None:
            self.report_error(
                "Blank assistant reply",
                extra_log=translations_string,
                message=True,
            )
            msg = "Blank assistant reply"
            raise MachineTranslationError(msg)

        # Ignore extra whitespace in response as OpenAI can be creative in that
        # (see https://github.com/WeblateOrg/weblate/issues/12456)
        translations = SEPARATOR_RE.split(translations_string)
        if not rephrase and len(translations) != len(texts):
            self.report_error(
                "Failed to parse assistant reply",
                extra_log=translations_string,
                message=True,
            )
            msg = f"Could not parse assistant reply, expected={len(texts)}, received={len(translations)}"
            raise MachineTranslationError(msg)

        for index, translation in enumerate(translations):
            text = texts[index if not rephrase else 0]
            result[text].append(
                {
                    "text": translation,
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                }
            )

    def get_model(self) -> str:
        raise NotImplementedError


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
