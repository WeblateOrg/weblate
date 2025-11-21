# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Urtzi Odriozola <urtzi.odriozola@ni.eus>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

import re
from collections import defaultdict
from itertools import chain
from typing import TYPE_CHECKING, Literal, overload

from weblate.glossary.models import (
    fetch_glossary_terms,
    get_glossary_terms,
    render_glossary_units_tsv,
)
from weblate.machinery.base import (
    BatchMachineTranslation,
    MachineTranslationError,
)
from weblate.machinery.forms import LLMBasicMachineryForm
from weblate.utils.errors import add_breadcrumb

if TYPE_CHECKING:
    from weblate.trans.models import Unit

    from .base import (
        DownloadMultipleTranslations,
    )

GENERATE_ENDPOINT = "/api/generate"

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


class BaseLLMTranslation(BatchMachineTranslation):
    name = "LLM"
    max_score = 90
    request_timeout = 60
    glossary_support = True
    settings_form = LLMBasicMachineryForm
    end_point = GENERATE_ENDPOINT

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

    def get_model(self) -> str:
        raise NotImplementedError

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

    def _fetch_llm_translations(self, prompt: str, content: str) -> str:
        return ""

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
            if (
                unit is not None
                and unit.translated
                and not unit.readonly
                and all(unit.get_target_plurals())
            ):
                rephrase.append((text, unit))
            else:
                texts.append(text)
                units.append(unit)

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
        prompt = self._get_prompt(
            source_language, target_language, texts, units, rephrase=rephrase
        )
        content = SEPARATOR.join(texts if not rephrase else [*texts, units[0].target])
        add_breadcrumb(self.name, "prompt", prompt=prompt)
        add_breadcrumb(self.name, "chat", content=content)

        translations_string = self._fetch_llm_translations(prompt, content)

        add_breadcrumb(self.name, "response", translations_string=translations_string)
        if translations_string is None:
            self.report_error(
                "Blank assistant reply",
                extra_log=translations_string,
                message=True,
            )
            msg = "Blank assistant reply"
            raise MachineTranslationError(msg)

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
