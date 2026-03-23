# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Urtzi Odriozola <urtzi.odriozola@ni.eus>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

import json
from collections import defaultdict
from itertools import chain
from typing import TYPE_CHECKING, Literal

from weblate.glossary.models import (
    fetch_glossary_terms,
    get_glossary_terms,
    get_glossary_tuples,
)
from weblate.machinery.base import (
    BatchMachineTranslation,
    MachineTranslationError,
)
from weblate.utils.errors import add_breadcrumb

if TYPE_CHECKING:
    from weblate.trans.models import Unit

    from .base import DownloadMultipleTranslations

PROMPT = """
You are a professional translation engine specialized in structured localization tasks.

{persona}

{style}

Input is provided as JSON with the following schema:

{{
    "source_language": "xx",                    // source language code (ISO, gettext or BCP)
    "target_language": "xx",                    // target language code (ISO, gettext or BCP)
    "glossary": {{                              // glossary of specific terms to use while translating
        "source term": "target term",
    }},
    "strings": [                                // strings to translate
        {{
            "source": "source [X1X]string"      // text to translate with a non-translatable placeable
        }},
        {{
            "source": "another string"          // text to translate without placeables
        }},
        {{
            "source": "rephrased string",       // text to rephrase based on existing translation
            "translation": "existing translation"
        }}
    ]
}}

Rules:
1. Translate each string in "strings" in order, producing one output per input string.
2. Placeholders matching the regular expression \\[X\\d+X\\] must be preserved exactly (byte-identical). They may be reordered if required by target language grammar, but must not be modified, duplicated, or removed.
3. If a string has a "translation" field, use it as the base. Correct errors and improve fluency/style, but stay close to its meaning. Do not re-translate from source unless the existing translation is fundamentally wrong.
4. Apply glossary terms as written; inflect only when target language grammar requires it. Preserve original capitalization pattern unless the glossary specifies exact casing. Do not partially apply glossary entries.
5. Preserve tone, register, formatting, whitespace, and line breaks.
6. Do not add, omit, reinterpret, summarize, or expand content.
7. Do not transliterate or explain translations.
8.  Output must be entirely in the target_language except preserved placeholders.
9. Output must be valid JSON.
10. Output must be a single JSON array of strings.
11. Do not include markdown code fences or any additional text.
12. The number of output elements must exactly match the number of input strings.
13. Ensure all output strings are properly JSON-escaped.
14. Internally verify placeholder integrity and JSON validity before responding.

Respond ONLY with a valid JSON array of strings, one per input string, in the same order:

["translation 1", "translation 2", ...]
"""


class BaseLLMTranslation(BatchMachineTranslation):
    max_score = 90
    request_timeout = 120
    glossary_support = True

    def is_supported(self, source_language, target_language) -> bool:
        return True

    def format_prompt_part(self, name: Literal["style", "persona"]) -> str:
        text = self.settings[name]
        text = text.strip()
        if text and not text.endswith("."):
            text = f"{text}."
        return text

    def fetch_llm_translations(
        self, prompt: str, content: str, previous_content: str, previous_response: str
    ) -> str | None:
        raise NotImplementedError

    def _build_message(
        self,
        source_language: str,
        target_language: str,
        texts: list[dict[str, str]],
        glossary: dict[str, str],
    ) -> str:
        result = {
            "source_language": source_language,
            "target_language": target_language,
            "glossary": glossary,
            "strings": texts,
        }
        return json.dumps(result)

    def _get_message(
        self,
        source_language: str,
        target_language: str,
        sources: list[tuple[str, Unit | None]],
    ) -> str:
        glossary: dict[str, str] = {}

        units = [unit for _text, unit in sources if unit is not None]
        if units:
            fetch_glossary_terms(units)
            glossary = dict(
                get_glossary_tuples(
                    chain.from_iterable(
                        get_glossary_terms(unit, include_variants=False)
                        for unit in units
                    )
                )
            )

        inputs = []

        for text, unit in sources:
            if (
                unit is not None
                and unit.translated
                and not unit.readonly
                and all(unit.get_target_plurals())
            ):
                # TODO: probably should use plural mapper here
                inputs.append(
                    {"source": text, "translation": unit.get_target_plurals()[0]}
                )
            else:
                inputs.append({"source": text})

        return self._build_message(source_language, target_language, inputs, glossary)

    def _get_prompt(self) -> str:
        return PROMPT.format(
            persona=self.format_prompt_part("persona"),
            style=self.format_prompt_part("style"),
        )

    def download_multiple_translations(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = 75,
    ) -> DownloadMultipleTranslations:
        result: DownloadMultipleTranslations = defaultdict(list)

        prompt = self._get_prompt()
        content = self._get_message(source_language, target_language, sources)

        # Build previous messages for better anchoring assistant responses
        # TODO: This might use existing translations instead of hard-coded example
        previous_content = self._build_message(
            "en",
            "cs",
            [
                {
                    "source": f"Hello, {self.format_replacement(2, 2, '', None)}, how are you?"
                },
                {
                    "source": f"{self.format_replacement(1, 12, '', None)} failing checks"
                },
                {"source": "Good morning"},
            ],
            {"Hello": "Nazdar"},
        )
        previous_response = json.dumps(
            ["Nazdar [X2X], jak se máš?", "[X1X] selhavších kontrol", "Dobré ráno"],
        )
        add_breadcrumb(self.name, "prompt", prompt=prompt)
        add_breadcrumb(self.name, "chat", content=content)

        translations_string = self.fetch_llm_translations(
            prompt, content, previous_content, previous_response
        )

        add_breadcrumb(self.name, "response", translations_string=translations_string)
        if translations_string is None or not translations_string:
            msg = "Blank assistant reply"
            self.report_error(msg, extra_log=translations_string, message=True)
            raise MachineTranslationError(msg)

        try:
            translations = json.loads(translations_string)
        except json.JSONDecodeError as error:
            msg = "Could not parse assistant reply as JSON."
            self.report_error(msg, extra_log=translations_string)
            raise MachineTranslationError(msg) from error

        if (
            not isinstance(translations, list)
            or not all(isinstance(item, str) for item in translations)
            or len(translations) != len(sources)
        ):
            msg = "Mismatching assistant reply."
            self.report_error(msg, extra_log=translations_string, message=True)
            raise MachineTranslationError(msg)

        for index, translation in enumerate(translations):
            text = sources[index][0]
            result[text].append(
                {
                    "text": translation,
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                }
            )
        return result
