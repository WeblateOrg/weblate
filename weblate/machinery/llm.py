# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Urtzi Odriozola <urtzi.odriozola@ni.eus>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

import json
import re
import string
from collections import Counter, defaultdict
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
            "source": "source @@PH1@@string"    // text to translate with a non-translatable placeable
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
2. Placeholders matching the regular expression @@PH\\d+@@ must be preserved exactly (byte-identical). They may be reordered if required by target language grammar, but must not be modified, duplicated, or removed.
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
15. Placeholder contract: Tokens like @@PH44@@ are opaque atoms. Never translate, inflect, split, rename, reorder characters inside, wrap, or escape them. Never convert them to another syntax.
16. Markup contract: Preserve markup, tags, attributes, entities, and similar control sequences exactly. Translate only human-readable text outside markup and outside placeholder tokens.
17. Output contract: Return exactly one JSON array of strings, with no characters before `[` or after `]`.

Valid placeholder and markup handling:
["Click <a href=\"/x\">log out</a> and use @@PH195@@."]

Invalid placeholder handling:
["Click <a href=\"/x\">log out</a> and use \\@\\@PH195\\@\\@."]

Respond ONLY with a valid JSON array of strings, one per input string, in the same order:

["translation 1", "translation 2", ...]
"""

LLM_PLACEHOLDER_RE = re.compile(r"@@PH(?P<id>\d+)@@")
RECOVERABLE_LLM_PLACEHOLDER_RE = re.compile(r"@@PH(?P<id>\d+) *@ *@")
ESCAPED_LLM_PLACEHOLDER_RE = re.compile(r"(?:\\@){2}PH(?P<id>\d+) *\\@ *\\@")


class BaseLLMTranslation(BatchMachineTranslation):
    max_score = 90
    request_timeout = 120
    glossary_support = True
    replacement_start = "@@PH"
    replacement_end = "@@"

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

    def make_re_placeholder(self, text: str) -> str:
        if LLM_PLACEHOLDER_RE.fullmatch(text):
            return f"{re.escape(text[:-2])} *{re.escape(text[-2:-1])} *{re.escape(text[-1:])}"
        return super().make_re_placeholder(text)

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

    @staticmethod
    def _skip_json_whitespace(content: str, index: int) -> int:
        while index < len(content) and content[index] in " \t\r\n":
            index += 1
        return index

    @classmethod
    def _repair_placeholder_escape(
        cls, content: str, index: int
    ) -> tuple[str | None, int]:
        llm_placeholder_match = ESCAPED_LLM_PLACEHOLDER_RE.match(content, index)
        if llm_placeholder_match is not None:
            return (
                f"@@PH{llm_placeholder_match.group('id')}@@",
                llm_placeholder_match.end(),
            )

        return None, index

    @staticmethod
    def _has_valid_unicode_escape(content: str, index: int) -> bool:
        return (
            index + 6 <= len(content)
            and content[index + 1] == "u"
            and all(
                character in string.hexdigits
                for character in content[index + 2 : index + 6]
            )
        )

    @classmethod
    def _repair_json_string(cls, content: str, index: int) -> tuple[str | None, int]:
        if index >= len(content) or content[index] != '"':
            return None, index

        repaired = ['"']
        index += 1

        while index < len(content):
            char = content[index]

            if char == "\\":
                if index + 1 >= len(content):
                    return None, index

                placeholder, next_index = cls._repair_placeholder_escape(content, index)
                if placeholder is not None:
                    repaired.append(placeholder)
                    index = next_index
                    continue

                next_char = content[index + 1]
                if next_char in {'"', "\\", "/", "b", "f", "n", "r", "t"}:
                    repaired.extend((char, next_char))
                    index += 2
                    continue

                if next_char == "u" and cls._has_valid_unicode_escape(content, index):
                    repaired.append(content[index : index + 6])
                    index += 6
                    continue

                repaired.extend(("\\\\", next_char))
                index += 2
                continue

            if char == '"':
                next_index = cls._skip_json_whitespace(content, index + 1)
                if next_index < len(content) and content[next_index] == '"':
                    return None, index
                if next_index < len(content) and content[next_index] not in {",", "]"}:
                    repaired.append('\\"')
                    index += 1
                    continue

                repaired.append(char)
                return "".join(repaired), index + 1

            repaired.append(char)
            index += 1

        return None, index

    @classmethod
    def _repair_json_string_array(cls, content: str) -> str | None:
        index = cls._skip_json_whitespace(content, 0)
        if index >= len(content) or content[index] != "[":
            return None

        repaired = ["["]
        index += 1
        item_count = 0

        while True:
            index = cls._skip_json_whitespace(content, index)
            if index >= len(content):
                return None

            if content[index] == "]":
                repaired.append("]")
                index += 1
                break

            if item_count:
                if content[index] != ",":
                    return None
                repaired.append(",")
                index += 1
                index = cls._skip_json_whitespace(content, index)

            string_item, index = cls._repair_json_string(content, index)
            if string_item is None:
                return None

            repaired.append(string_item)
            item_count += 1

        if cls._skip_json_whitespace(content, index) != len(content):
            return None

        return "".join(repaired)

    @classmethod
    def _iter_placeholders(cls, text: str) -> list[tuple[str, int]]:
        return [
            (f"@@PH{match.group('id')}@@", match.end())
            for match in RECOVERABLE_LLM_PLACEHOLDER_RE.finditer(text)
        ]

    @classmethod
    def _extract_placeholders(cls, text: str) -> Counter[str]:
        return Counter(token for token, _end in cls._iter_placeholders(text))

    @classmethod
    def _extract_literal_at_suffixes(cls, text: str) -> Counter[str]:
        suffixes: Counter[str] = Counter()
        for token, end in cls._iter_placeholders(text):
            if end >= len(text) or text[end] != "@":
                continue
            if text.startswith("@@PH", end):
                continue
            suffixes[token] += 1
        return suffixes

    @classmethod
    def _validate_translations(
        cls,
        translations: object,
        sources: list[tuple[str, Unit | None]],
    ) -> list[str]:
        if (
            not isinstance(translations, list)
            or not all(isinstance(item, str) for item in translations)
            or len(translations) != len(sources)
        ):
            msg = "Mismatching assistant reply."
            raise MachineTranslationError(msg)

        for index, translation in enumerate(translations):
            source_text = sources[index][0]
            if cls._extract_placeholders(translation) != cls._extract_placeholders(
                source_text
            ):
                msg = "Mismatching assistant reply."
                raise MachineTranslationError(msg)
            if cls._extract_literal_at_suffixes(
                translation
            ) != cls._extract_literal_at_suffixes(source_text):
                msg = "Mismatching assistant reply."
                raise MachineTranslationError(msg)

        return translations

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
                {
                    "source": f'To continue, click <a href="/x">log out</a> and use {self.format_replacement(195, 195, "", None)}.'
                },
            ],
            {"Hello": "Nazdar"},
        )
        previous_response = json.dumps(
            [
                f"Nazdar {self.format_replacement(2, 2, '', None)}, jak se máš?",
                f"{self.format_replacement(1, 12, '', None)} selhavších kontrol",
                "Dobré ráno",
                f'Chcete-li pokračovat, klikněte na <a href="/x">odhlásit se</a> a použijte {self.format_replacement(195, 195, "", None)}.',
            ],
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
            repaired_translations_string = self._repair_json_string_array(
                translations_string
            )
            if repaired_translations_string is None:
                msg = "Could not parse assistant reply as JSON."
                self.report_error(msg, extra_log=translations_string)
                raise MachineTranslationError(msg) from error

            try:
                translations = json.loads(repaired_translations_string)
            except json.JSONDecodeError as repaired_error:
                msg = "Could not parse assistant reply as JSON."
                self.report_error(msg, extra_log=translations_string)
                raise MachineTranslationError(msg) from repaired_error

            add_breadcrumb(self.name, "response-repaired")

        try:
            translations = self._validate_translations(translations, sources)
        except MachineTranslationError as error:
            msg = "Mismatching assistant reply."
            self.report_error(msg, extra_log=translations_string, message=True)
            raise MachineTranslationError(msg) from error

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
