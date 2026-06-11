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
from operator import itemgetter
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, TypeGuard

from django.utils.html import strip_tags
from django.utils.translation import override, pgettext

from weblate.checks.utils import highlight_string
from weblate.glossary.models import (
    cleanup_glossary_term,
    fetch_glossary_terms,
    get_glossary_terms,
)
from weblate.lang.models import Language, PluralMapper
from weblate.machinery.base import (
    MACHINERY_DEFAULT_THRESHOLD,
    BatchMachineTranslation,
    MachineTranslationError,
)
from weblate.utils.errors import add_breadcrumb
from weblate.utils.hash import calculate_hash, hash_to_checksum
from weblate.utils.state import STATE_READONLY, STATE_TRANSLATED
from weblate.utils.translation import pgettext_noop

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from weblate.lang.models import Plural
    from weblate.trans.models import Component, Translation, Unit

    from .base import (
        DownloadMultipleTranslations,
        SettingsDict,
        TranslationResultDict,
    )

type JSONValue = (
    bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None
)

PROMPT = """
You are a professional translation engine specialized in structured localization tasks.

{persona}

{style}

{language_instructions}

Input is provided as JSON with the following schema:

{{
    "source_language": "xx",                    // source language code (ISO, gettext or BCP)
    "target_language": "xx",                    // target language code (ISO, gettext or BCP)
    "glossary": [                               // glossary of specific terms to use while translating
        {{
            "source": "source term",
            "target": "target term",
            "source_explanation": "source meaning or usage",       // optional
            "target_explanation": "target meaning or usage",       // optional
            "flags": ["read-only", "terminology"]                  // optional
        }}
    ],
    "strings": [                                // strings to translate
        {{
            "source": "source @@PH1@@string",   // text to translate with a non-translatable placeable
            "context": "gettext context",       // optional source context for bilingual strings
            "key": "app.menu.save",             // optional key for monolingual strings
            "explanation": "button label",      // optional explanation of meaning or usage
            "secondary": {{                     // optional translation in configured secondary language
                "language": "xx",
                "text": "secondary language text"
            }},
            "plural": {{                        // optional plural metadata for this string
                "form_index": 0,
                "source_forms": 2,
                "target_forms": 3,
                "source_formula": "nplurals=2; plural=n != 1;",
                "target_formula": "nplurals=3; plural=..."
            }},
            "failing_checks": [                 // optional active failing quality checks
                {{
                    "check_id": "same",
                    "name": "Unchanged translation",
                    "description": "Source and translation are identical."
                }}
            ],
            "placeholders": {{                  // optional mapping of opaque tokens to original content
                "@@PH1@@": "%s"
            }}
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
4. Apply glossary terms as written; inflect only when target language grammar requires it. Use glossary explanations and flags to disambiguate duplicate source terms. Preserve original capitalization pattern unless the glossary specifies exact casing. Do not partially apply glossary entries.
5. Preserve tone, register, formatting, whitespace, and line breaks.
6. Do not add, omit, reinterpret, summarize, or expand content.
7. Do not transliterate or explain translations.
8.  Output must be entirely in the target_language except preserved placeholders.
9. Output must be valid JSON.
10. Output must be a single JSON array of strings.
11. Do not include markdown code fences or any additional text.
12. The number of output elements must exactly match the number of input strings. Do not emit empty extra strings.
13. Ensure all output strings are properly JSON-escaped.
14. Internally verify placeholder integrity and JSON validity before responding.
15. Placeholder contract: Tokens like @@PH44@@ are opaque atoms. Never translate, inflect, split, rename, reorder characters inside, wrap, or escape them. Never convert them to another syntax.
16. Markup contract: Preserve markup, tags, attributes, entities, and similar control sequences exactly. Translate only human-readable text outside markup and outside placeholder tokens.
17. Output contract: Return exactly one JSON array of strings, with no characters before `[` or after `]`.
18. Treat context, key, explanation, secondary, plural, failing_checks, and placeholders fields as reference material only. Do not translate them directly and do not add their contents unless they are present in source.
19. Placeholder mappings explain what opaque placeholder tokens represent. This information may guide wording, but the output must still contain the exact placeholder tokens, not the mapped content.
20. Failing checks describe issues to avoid or fix when improving an existing translation.
21. Target-language project instructions, when present above, contain additional requirements for the target language. Follow them unless they conflict with preserving the source meaning, placeholders, markup, or output contract.
22. For translatable markup placeholders that wrap text, translate the whole text between the placeholders. Example: @@PH1@@Reset and reapply@@PH2@@ can become @@PH1@@Zurucksetzen und erneut anwenden@@PH2@@, never @@PH1@@Zurucksetzen und @@PH2@@erneut anwenden@@PH2@@.

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
LANGUAGE_CODE_PART_RE = re.compile(r"[-_@]")
LLM_PREVIOUS_EXAMPLE_LIMIT = 4
LLM_GLOSSARY_FLAGS = ("read-only", "terminology")
LLM_CURATED_PREVIOUS_EXAMPLE_SOURCES = (
    pgettext_noop("LLM translation example", "Hello, @@PH1@@!"),
    pgettext_noop("LLM translation example", 'Click <a href="/x">Save</a>.'),
    pgettext_noop("LLM translation example", "@@PH1@@ failed checks"),
)
LLM_NEUTRAL_PREVIOUS_EXAMPLE_SOURCES = (
    "@@PH1@@",
    "Weblate",
    "<code>API</code> @@PH2@@",
)


class LLMGlossaryEntry(TypedDict, total=False):
    source: str
    target: str
    source_explanation: str
    target_explanation: str
    flags: list[str]


class LLMPreviousExample(TypedDict):
    source: str
    target: str


class LLMSecondaryContext(TypedDict):
    language: str
    text: str
    language_name: NotRequired[str]


class LLMPluralContext(TypedDict):
    source_forms: int
    target_forms: int
    form_index: NotRequired[int]
    source_formula: NotRequired[str]
    target_formula: NotRequired[str]


class LLMFailingCheckContext(TypedDict):
    check_id: str
    name: NotRequired[str]
    description: NotRequired[str]


class LLMStringContext(TypedDict, total=False):
    context: str
    key: str
    explanation: str
    secondary: LLMSecondaryContext
    plural: LLMPluralContext
    failing_checks: list[LLMFailingCheckContext]
    placeholders: dict[str, str]


class LLMStringPayload(LLMStringContext):
    source: str
    translation: NotRequired[str]


class BaseLLMTranslation(BatchMachineTranslation):
    max_score = 90
    request_timeout = 120
    glossary_support = True
    llm_context_support = True
    replacement_start = "@@PH"
    replacement_end = "@@"

    def __init__(self, configuration: SettingsDict) -> None:
        super().__init__(configuration)
        self._secondary_context_cache: dict[tuple[int, int], Unit | None] | None = None

    def is_supported(self, source_language, target_language) -> bool:
        return True

    @staticmethod
    def format_prompt_text(text: str) -> str:
        text = text.strip()
        if text and not text.endswith("."):
            text = f"{text}."
        return text

    def format_prompt_part(self, name: Literal["style", "persona"]) -> str:
        return self.format_prompt_text(self.settings[name])

    def format_language_instructions(self, target_language: str) -> str:
        text = self.format_prompt_text(self._get_language_instructions(target_language))
        if not text:
            return ""
        return f"Target-language project instructions:\n{text}"

    def fetch_llm_translations(
        self, prompt: str, content: str, previous_content: str, previous_response: str
    ) -> str | None:
        raise NotImplementedError

    @staticmethod
    def _normalize_context_text(text: str | None) -> str:
        if text is None:
            return ""
        return text.strip()

    @staticmethod
    def _normalize_check_text(text: StrOrPromise | None) -> str:
        if text is None:
            return ""
        return " ".join(strip_tags(str(text)).split())

    @staticmethod
    def _get_language_id(language: Language | None) -> int | None:
        return getattr(language, "id", None) or getattr(language, "pk", None)

    @classmethod
    def _get_language_name(cls, language: Language) -> str:
        return cls._normalize_context_text(language.get_name())

    def get_uncached_pending_key(self, index: int, text: str, unit: Unit | None) -> str:
        return f"pending:{index}"

    def _ensure_secondary_context_cache(self) -> bool:
        if self._secondary_context_cache is not None:
            return False
        self._secondary_context_cache = {}
        return True

    def _clear_secondary_context_cache(self, started_cache: bool) -> None:
        if started_cache:
            self._secondary_context_cache = None

    def _translate_sources(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> list[list[TranslationResultDict]]:
        started_cache = self._ensure_secondary_context_cache()
        try:
            return super()._translate_sources(
                source_language, target_language, sources, user, threshold
            )
        finally:
            self._clear_secondary_context_cache(started_cache)

    @staticmethod
    def _get_related_language_id(
        obj: Component | Translation, field: Literal["language", "source_language"]
    ) -> int | None:
        if language_id := getattr(obj, f"{field}_id", None):
            return language_id
        return BaseLLMTranslation._get_language_id(getattr(obj, field, None))

    @staticmethod
    def _get_effective_secondary_language(
        component: Component | None,
    ) -> Language | None:
        if component is None:
            return None
        try:
            return component.effective_secondary_language
        except AttributeError:
            return getattr(component, "secondary_language", None) or getattr(
                getattr(component, "project", None), "secondary_language", None
            )

    @staticmethod
    def _is_monolingual_unit(unit: Unit) -> bool:
        component = getattr(getattr(unit, "translation", None), "component", None)
        if component is None:
            return False

        has_template = getattr(component, "has_template", None)
        if has_template is not None:
            return bool(has_template())

        file_format = getattr(component, "file_format_cls", None)
        return bool(getattr(file_format, "monolingual", False))

    @classmethod
    def _get_explanation_context(cls, unit: Unit) -> str:
        source_unit = getattr(unit, "source_unit", None)
        if source_unit is not None:
            explanation = cls._normalize_context_text(
                getattr(source_unit, "explanation", "")
            )
            if explanation:
                return explanation

        return cls._normalize_context_text(getattr(unit, "explanation", ""))

    @classmethod
    def _get_failing_checks_context(
        cls, unit: Unit, *, include_labels: bool = True
    ) -> list[LLMFailingCheckContext]:
        checks = getattr(unit, "active_checks", None)
        if checks is None:
            all_checks = getattr(unit, "all_checks", None)
            if all_checks is None:
                return []
            checks = [
                check for check in all_checks if not getattr(check, "dismissed", False)
            ]

        result: list[LLMFailingCheckContext] = []
        for check in checks:
            check_id = cls._normalize_context_text(check.name)
            if check_id:
                item: LLMFailingCheckContext = {"check_id": check_id}
                if include_labels:
                    with override("en"):
                        name = cls._normalize_check_text(check.get_name())
                        if name:
                            item["name"] = name
                        description = cls._normalize_check_text(check.get_description())
                        if description:
                            item["description"] = description
                result.append(item)

        result.sort(
            key=lambda item: (
                item["check_id"],
                item.get("name", ""),
                item.get("description", ""),
            )
        )
        return result

    def make_re_placeholder(self, text: str) -> str:
        if LLM_PLACEHOLDER_RE.fullmatch(text):
            return f"{re.escape(text[:-2])} *{re.escape(text[-2:-1])} *{re.escape(text[-1:])}"
        return super().make_re_placeholder(text)

    def _build_message(
        self,
        source_language: str,
        target_language: str,
        texts: list[LLMStringPayload],
        glossary: list[LLMGlossaryEntry],
    ) -> str:
        result = {
            "source_language": source_language,
            "target_language": target_language,
            "glossary": glossary,
            "strings": texts,
        }
        return json.dumps(result)

    @staticmethod
    def _get_language_base_code(language: str) -> str:
        return LANGUAGE_CODE_PART_RE.split(language, 1)[0]

    @classmethod
    def _is_english_language(cls, language: str) -> bool:
        return cls._get_language_base_code(language).lower() == "en"

    def _get_language_instructions(self, target_language: str) -> str:
        instructions = self.settings.get("language_instructions") or {}
        if not isinstance(instructions, dict):
            return ""

        text = instructions.get(target_language)
        if isinstance(text, str) and (text := text.strip()):
            return text

        target = Language.objects.fuzzy_get_strict(target_language)
        base_language = self._get_language_base_code(target_language)
        if target is not None:
            for language, text in instructions.items():
                if (
                    not isinstance(language, str)
                    or language == base_language
                    or not isinstance(text, str)
                ):
                    continue
                matched_language = Language.objects.fuzzy_get_strict(language)
                if matched_language == target and (text := text.strip()):
                    return text

        text = instructions.get(base_language)
        if isinstance(text, str) and (text := text.strip()):
            return text
        return ""

    @classmethod
    def _get_glossary_entry(cls, unit: Unit) -> LLMGlossaryEntry | None:
        flags = unit.all_flags
        if "forbidden" in flags:
            return None

        if not unit.translated and "read-only" not in flags:
            return None

        source = cleanup_glossary_term(unit.source)
        target = source if "read-only" in flags else cleanup_glossary_term(unit.target)
        if not source or not target:
            return None

        entry: LLMGlossaryEntry = {
            "source": source,
            "target": target,
        }

        source_unit = getattr(unit, "source_unit", None)
        if source_explanation := cls._normalize_context_text(
            getattr(source_unit, "explanation", "")
        ):
            entry["source_explanation"] = source_explanation

        if target_explanation := cls._normalize_context_text(
            getattr(unit, "explanation", "")
        ):
            entry["target_explanation"] = target_explanation

        glossary_flags = [flag for flag in LLM_GLOSSARY_FLAGS if flag in flags]
        if glossary_flags:
            entry["flags"] = glossary_flags

        return entry

    @classmethod
    def _get_glossary_entries(cls, units: list[Unit]) -> list[LLMGlossaryEntry]:
        result: list[LLMGlossaryEntry] = []
        included: set[str] = set()
        for term in chain.from_iterable(
            get_glossary_terms(unit, include_variants=False) for unit in units
        ):
            entry = cls._get_glossary_entry(term)
            if entry is None:
                continue

            cache_key = json.dumps(entry, sort_keys=True)
            if cache_key in included:
                continue

            included.add(cache_key)
            result.append(entry)
        return result

    def get_llm_glossary_cache_part(self, unit: Unit) -> str:
        try:
            fetch_glossary_terms([unit], include_variants=False)
            entries = self._get_glossary_entries([unit])
        except (AttributeError, TypeError, ValueError):
            return ""
        return hash_to_checksum(calculate_hash(json.dumps(entries, sort_keys=True)))

    @classmethod
    def _get_placeholder_context(
        cls, source_text: str, unit: Unit | None, source_occurrence: int = 0
    ) -> dict[str, str]:
        placeholder_specs = cls._iter_source_placeholder_specs(
            source_text, unit, source_occurrence
        )
        if not placeholder_specs:
            return {}
        return dict(placeholder_specs)

    @classmethod
    def _find_plural_indexes(cls, source_text: str, unit: Unit) -> list[int]:
        for source_variants in (
            getattr(unit, "plural_map", ()),
            unit.get_source_plurals(),
        ):
            result: list[int] = []
            for index, source_variant in enumerate(source_variants):
                cleaned_source, _specs = cls._cleanup_source_variant(
                    source_variant, unit
                )
                if cleaned_source == source_text:
                    result.append(index)
            if result:
                return result

        return []

    @classmethod
    def _find_plural_index(
        cls, source_text: str, unit: Unit, source_occurrence: int = 0
    ) -> int | None:
        plural_indexes = cls._find_plural_indexes(source_text, unit)
        if not plural_indexes:
            return None
        if source_occurrence < len(plural_indexes):
            return plural_indexes[source_occurrence]
        return plural_indexes[0]

    @classmethod
    def _get_plural_context(
        cls,
        source_text: str,
        unit: Unit,
        source_language: str | None,
        source_occurrence: int = 0,
    ) -> LLMPluralContext | None:
        plural_map = getattr(unit, "plural_map", ())
        source_plurals = unit.get_source_plurals()
        if not (
            getattr(unit, "is_plural", False)
            or len(source_plurals) > 1
            or len(plural_map) > 1
        ):
            return None

        source_plural = cls._get_source_plural(unit, source_language)
        source_forms = getattr(source_plural, "number", len(source_plurals))
        target_plural = getattr(getattr(unit, "translation", None), "plural", None)
        target_forms = getattr(target_plural, "number", len(unit.get_target_plurals()))

        result: LLMPluralContext = {
            "source_forms": source_forms,
            "target_forms": target_forms,
        }

        if (
            form_index := cls._find_plural_index(source_text, unit, source_occurrence)
        ) is not None:
            result["form_index"] = form_index

        if source_formula := getattr(source_plural, "plural_form", ""):
            result["source_formula"] = source_formula
        if target_formula := getattr(target_plural, "plural_form", ""):
            result["target_formula"] = target_formula

        return result

    @classmethod
    def _get_source_plural(
        cls, unit: Unit, source_language: str | None
    ) -> Plural | None:
        translation = getattr(unit, "translation", None)
        component = getattr(translation, "component", None)
        if component is None:
            return None

        language_code = source_language
        try:
            secondary_candidates: tuple[Language | None, ...] = (
                component.effective_secondary_language,
            )
        except AttributeError:
            secondary_candidates = (
                getattr(component, "secondary_language", None),
                getattr(
                    getattr(component, "project", None), "secondary_language", None
                ),
            )
        candidates = (
            getattr(component, "source_language", None),
            *secondary_candidates,
            getattr(translation, "language", None),
        )
        for language in candidates:
            if language is None:
                continue
            if (
                language_code is not None
                and getattr(language, "code", None) != language_code
            ):
                continue
            return getattr(language, "plural", None)

        return getattr(getattr(component, "source_language", None), "plural", None)

    @staticmethod
    def _get_secondary_unit(
        unit_set,
        unit: Unit,
        secondary_language: Language,
        secondary_language_id: int | None,
    ) -> Unit | None:
        if secondary_language_id is None:
            query = unit_set.filter(translation__language=secondary_language)
        else:
            query = unit_set.filter(translation__language_id=secondary_language_id)
        query = (
            query.filter(state__gte=STATE_TRANSLATED, state__lt=STATE_READONLY)
            .exclude(target="")
            .select_related("translation__language")
        )
        if unit_pk := getattr(unit, "pk", None):
            query = query.exclude(pk=unit_pk)
        return query.first()

    def _get_secondary_context(
        self,
        source_text: str,
        unit: Unit,
        source_occurrence: int = 0,
    ) -> LLMSecondaryContext | None:
        translation = getattr(unit, "translation", None)
        component = getattr(translation, "component", None)
        if translation is None or component is None:
            return None

        secondary_language = self._get_effective_secondary_language(component)
        if secondary_language is None:
            return None

        secondary_language_id = self._get_language_id(secondary_language)
        if secondary_language_id in {
            self._get_related_language_id(translation, "language"),
            self._get_related_language_id(component, "source_language"),
        }:
            return None

        source_unit = getattr(unit, "source_unit", None) or unit
        unit_set = getattr(source_unit, "unit_set", None)
        if unit_set is None:
            return None

        source_unit_id = getattr(source_unit, "id", None) or getattr(
            source_unit, "pk", None
        )
        cache_key = (
            source_unit_id if isinstance(source_unit_id, int) else id(source_unit),
            secondary_language_id
            if secondary_language_id is not None
            else id(secondary_language),
        )
        secondary_context_cache = self._secondary_context_cache
        if secondary_context_cache is not None and cache_key in secondary_context_cache:
            secondary_unit = secondary_context_cache[cache_key]
        else:
            try:
                secondary_unit = self._get_secondary_unit(
                    unit_set, unit, secondary_language, secondary_language_id
                )
            except (AttributeError, TypeError, ValueError):
                return None
            if secondary_context_cache is not None:
                secondary_context_cache[cache_key] = secondary_unit

        if secondary_unit is None:
            return None

        targets = secondary_unit.get_target_plurals()
        form_index = self._find_plural_index(source_text, unit, source_occurrence)
        if form_index is not None and form_index < len(targets) and targets[form_index]:
            text = targets[form_index]
        else:
            text = next((target for target in targets if target), "")
        if not text:
            return None

        result: LLMSecondaryContext = {
            "language": str(getattr(secondary_language, "code", secondary_language)),
            "text": text,
        }
        language_name = self._get_language_name(secondary_language)
        if language_name and language_name != result["language"]:
            result["language_name"] = language_name
        return result

    def _get_string_context(
        self,
        source_text: str,
        unit: Unit | None,
        source_language: str | None = None,
        *,
        include_check_labels: bool = True,
        source_occurrence: int = 0,
    ) -> LLMStringContext:
        if unit is None:
            return {}

        result: LLMStringContext = {}

        if context := self._normalize_context_text(getattr(unit, "context", "")):
            if self._is_monolingual_unit(unit):
                result["key"] = context
            else:
                result["context"] = context

        if explanation := self._get_explanation_context(unit):
            result["explanation"] = explanation

        if secondary := self._get_secondary_context(
            source_text, unit, source_occurrence
        ):
            result["secondary"] = secondary

        if plural := self._get_plural_context(
            source_text, unit, source_language, source_occurrence
        ):
            result["plural"] = plural

        if failing_checks := self._get_failing_checks_context(
            unit, include_labels=include_check_labels
        ):
            result["failing_checks"] = failing_checks

        if placeholders := self._get_placeholder_context(
            source_text, unit, source_occurrence
        ):
            result["placeholders"] = placeholders

        return result

    def _build_string_payload(
        self,
        source_text: str,
        unit: Unit | None,
        source_language: str | None = None,
        source_occurrence: int = 0,
    ) -> LLMStringPayload:
        return {
            "source": source_text,
            **self._get_string_context(
                source_text, unit, source_language, source_occurrence=source_occurrence
            ),
        }

    def get_translation_cache_extra_parts(
        self,
        index: int,
        text: str,
        unit: Unit | None,
        source_occurrence: int,
    ) -> tuple[str | int, ...]:
        if unit is None or source_occurrence == 0:
            return ()

        plural_map = getattr(unit, "plural_map", ())
        source_plurals = unit.get_source_plurals()
        if not (
            getattr(unit, "is_plural", False)
            or len(source_plurals) > 1
            or len(plural_map) > 1
        ):
            return ()

        plural_indexes = self._find_plural_indexes(text, unit)
        if len(plural_indexes) <= 1 or source_occurrence >= len(plural_indexes):
            return ()
        return ("plural-form", plural_indexes[source_occurrence])

    def get_translation_cache_parts(
        self,
        unit,
        source_language,
        target_language,
        text,
        threshold,
        replacements,
        *,
        source_occurrence: int = 0,
    ) -> tuple[str, ...]:
        result = (
            self.get_glossary_cache_part(unit),
            self.get_llm_glossary_cache_part(unit),
            *super().get_translation_cache_parts(
                unit,
                source_language,
                target_language,
                text,
                threshold,
                replacements,
                source_occurrence=source_occurrence,
            ),
        )
        context = self._get_string_context(
            text,
            unit,
            source_language,
            include_check_labels=False,
            source_occurrence=source_occurrence,
        )
        if context:
            return (
                hash_to_checksum(calculate_hash(json.dumps(context, sort_keys=True))),
                *result,
            )
        return result

    def _get_message(
        self,
        source_language: str,
        target_language: str,
        sources: list[tuple[str, Unit | None]],
        source_occurrences: list[int] | None = None,
    ) -> str:
        glossary: list[LLMGlossaryEntry] = []

        units = [unit for _text, unit in sources if unit is not None]
        if units:
            missing_glossary_terms = [
                unit for unit in units if getattr(unit, "glossary_terms", None) is None
            ]
            if missing_glossary_terms:
                fetch_glossary_terms(missing_glossary_terms, include_variants=False)
            glossary = self._get_glossary_entries(units)

        inputs = []
        occurrence_counts: dict[tuple[int | None, str], int] = defaultdict(int)

        for index, (text, unit) in enumerate(sources):
            if source_occurrences is None:
                occurrence_key = (id(unit) if unit is not None else None, text)
                source_occurrence = occurrence_counts[occurrence_key]
                occurrence_counts[occurrence_key] += 1
            else:
                source_occurrence = source_occurrences[index]

            payload = self._build_string_payload(
                text, unit, source_language, source_occurrence
            )
            if (
                unit is not None
                and unit.translated
                and not unit.readonly
                and all(unit.get_target_plurals())
            ):
                # TODO: probably should use plural mapper here
                translation = self._placeholderize_existing_translation(
                    unit.get_target_plurals()[0], text, unit
                )
                if translation is not None:
                    payload["translation"] = translation
                inputs.append(payload)
            else:
                inputs.append(payload)

        return self._build_message(
            source_language,
            target_language,
            inputs,
            glossary,
        )

    def _get_prompt(self, target_language: str) -> str:
        return PROMPT.format(
            persona=self.format_prompt_part("persona"),
            style=self.format_prompt_part("style"),
            language_instructions=self.format_language_instructions(target_language),
        )

    @classmethod
    def _get_project_example_source_plurals(
        cls, unit: Unit, source_language: str
    ) -> list[str]:
        translation = getattr(unit, "translation", None)
        component = getattr(translation, "component", None)
        target_plural = getattr(translation, "plural", None)
        component_source_language = getattr(component, "source_language", None)
        if getattr(component_source_language, "code", None) == source_language:
            source_plural = getattr(component_source_language, "plural", None)
            if source_plural is not None and target_plural is not None:
                return PluralMapper(source_plural, target_plural).map(unit)
            return unit.get_source_plurals()

        secondary_language = cls._get_effective_secondary_language(component)
        if getattr(secondary_language, "code", None) != source_language:
            return []

        source_unit = getattr(unit, "source_unit", None) or unit
        unit_set = getattr(source_unit, "unit_set", None)
        if unit_set is None:
            return []

        try:
            secondary_unit = cls._get_secondary_unit(
                unit_set,
                unit,
                secondary_language,
                cls._get_language_id(secondary_language),
            )
        except (AttributeError, TypeError, ValueError):
            return []

        if secondary_unit is None:
            return []

        source_plural = getattr(secondary_language, "plural", None)
        if source_plural is not None and target_plural is not None:
            return PluralMapper(source_plural, target_plural).map(unit, secondary_unit)
        return secondary_unit.get_target_plurals()

    def _get_project_previous_examples(
        self,
        source_language: str,
        sources: list[tuple[str, Unit | None]],
    ) -> list[LLMPreviousExample]:
        units = [unit for _text, unit in sources if unit is not None]
        if not units:
            return []

        translation = getattr(units[0], "translation", None)
        unit_set = getattr(translation, "unit_set", None)
        if unit_set is None:
            return []

        current_unit_ids = [
            unit_id
            for unit in units
            if (unit_id := getattr(unit, "pk", None)) is not None
        ]

        try:
            candidates = unit_set.filter(
                state__gte=STATE_TRANSLATED,
                state__lt=STATE_READONLY,
            ).exclude(target="")
            if current_unit_ids:
                candidates = candidates.exclude(pk__in=current_unit_ids)
            candidates = candidates.order_by("-last_updated")[
                : LLM_PREVIOUS_EXAMPLE_LIMIT * 4
            ]
        except (AttributeError, TypeError, ValueError):
            return []

        examples: list[LLMPreviousExample] = []
        for unit in candidates:
            source_plurals = self._get_project_example_source_plurals(
                unit, source_language
            )
            if not source_plurals:
                continue
            previous_plural_map = unit.plural_map
            unit.plural_map = source_plurals
            try:
                for source, target in zip(
                    source_plurals, unit.get_target_plurals(), strict=False
                ):
                    if not source or not target:
                        continue
                    cleaned_source, _replacements = self.cleanup_text(source, unit)
                    if not cleaned_source:
                        continue
                    cleaned_target = self._placeholderize_existing_translation(
                        target, cleaned_source, unit
                    )
                    if cleaned_target is None:
                        continue
                    if self._extract_placeholders(
                        cleaned_source
                    ) != self._extract_placeholders(cleaned_target):
                        continue

                    examples.append(
                        {
                            "source": cleaned_source,
                            "target": cleaned_target,
                        }
                    )
                    break
            finally:
                unit.plural_map = previous_plural_map
            if len(examples) >= LLM_PREVIOUS_EXAMPLE_LIMIT:
                break

        return examples

    @classmethod
    def _get_curated_previous_examples(
        cls, source_language: str, target_language: str
    ) -> list[LLMPreviousExample]:
        with override(source_language):
            sources = [
                cls._normalize_context_text(pgettext("LLM translation example", source))
                for source in LLM_CURATED_PREVIOUS_EXAMPLE_SOURCES
            ]

        with override(target_language):
            targets = [
                cls._normalize_context_text(pgettext("LLM translation example", source))
                for source in LLM_CURATED_PREVIOUS_EXAMPLE_SOURCES
            ]

        if not cls._is_english_language(source_language) and any(
            not example_source or example_source == source
            for source, example_source in zip(
                LLM_CURATED_PREVIOUS_EXAMPLE_SOURCES, sources, strict=True
            )
        ):
            return []

        if not cls._is_english_language(target_language) and any(
            not target or target == source
            for source, target in zip(
                LLM_CURATED_PREVIOUS_EXAMPLE_SOURCES, targets, strict=True
            )
        ):
            return []

        examples: list[LLMPreviousExample] = []
        for original_source, example_source, target in zip(
            LLM_CURATED_PREVIOUS_EXAMPLE_SOURCES, sources, targets, strict=True
        ):
            if cls._extract_placeholders(original_source) != cls._extract_placeholders(
                example_source
            ):
                return []
            if cls._extract_placeholders(original_source) != cls._extract_placeholders(
                target
            ):
                return []
            examples.append({"source": example_source, "target": target})
        return examples

    @staticmethod
    def _get_neutral_previous_examples() -> list[LLMPreviousExample]:
        return [
            {"source": source, "target": source}
            for source in LLM_NEUTRAL_PREVIOUS_EXAMPLE_SOURCES
        ]

    def _build_previous_messages_from_examples(
        self,
        source_language: str,
        target_language: str,
        examples: list[LLMPreviousExample],
    ) -> tuple[str, str]:
        return (
            self._build_message(
                source_language,
                target_language,
                [{"source": example["source"]} for example in examples],
                [],
            ),
            json.dumps([example["target"] for example in examples]),
        )

    def _get_previous_messages(
        self,
        source_language: str,
        target_language: str,
        sources: list[tuple[str, Unit | None]],
    ) -> tuple[str, str]:
        project_examples = self._get_project_previous_examples(source_language, sources)
        curated_examples = self._get_curated_previous_examples(
            source_language, target_language
        )
        if curated_examples:
            examples = [*curated_examples, *project_examples]
        else:
            examples = [*self._get_neutral_previous_examples(), *project_examples]

        return self._build_previous_messages_from_examples(
            source_language, target_language, examples
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
    def _iter_placeholder_matches(cls, text: str) -> list[tuple[int, int, str]]:
        return [
            (match.start(), match.end(), f"@@PH{match.group('id')}@@")
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
    def _cleanup_source_variant(
        cls, source_variant: str, unit: Unit
    ) -> tuple[str, list[tuple[str, str]]]:
        parts: list[str] = []
        specs: list[tuple[str, str]] = []
        start = 0
        for highlight_start, highlight_end, highlight_text in highlight_string(
            source_variant,
            unit,
            highlight_syntax=cls.highlight_syntax,
        ):
            token = f"{cls.replacement_start}{highlight_start}{cls.replacement_end}"
            parts.extend((source_variant[start:highlight_start], token))
            specs.append((token, highlight_text))
            start = highlight_end
        parts.append(source_variant[start:])
        return "".join(parts), specs

    @classmethod
    def _iter_source_placeholder_specs(
        cls, source_text: str, unit: Unit | None, source_occurrence: int = 0
    ) -> list[tuple[str, str]] | None:
        source_placeholders = [
            token for token, _end in cls._iter_placeholders(source_text)
        ]
        if unit is None:
            return [] if not source_placeholders else None

        source_variants = dict.fromkeys(
            chain(getattr(unit, "plural_map", ()), unit.get_source_plurals())
        )
        matching_specs: list[list[tuple[str, str]]] = []
        for source_variant in source_variants:
            cleaned_source, specs = cls._cleanup_source_variant(source_variant, unit)
            if cleaned_source == source_text:
                matching_specs.append(specs)

        if not matching_specs:
            return None
        if source_occurrence < len(matching_specs):
            return matching_specs[source_occurrence]
        return matching_specs[0]

    @classmethod
    def _iter_translation_highlights(
        cls,
        translation: str,
        unit: Unit,
        placeholder_matches: list[tuple[int, int, str]],
    ) -> list[tuple[int, int, str]]:
        highlights: list[tuple[int, int, str]] = []
        for start, end, highlight_text in highlight_string(
            translation, unit, highlight_syntax=cls.highlight_syntax
        ):
            if any(
                start < placeholder_end and end > placeholder_start
                for placeholder_start, placeholder_end, _token in placeholder_matches
            ):
                continue
            highlights.append((start, end, highlight_text))
        return highlights

    @classmethod
    def _placeholderize_translation(
        cls, translation: str, source_text: str, unit: Unit | None
    ) -> str | None:
        source_placeholders = [
            token for token, _end in cls._iter_placeholders(source_text)
        ]
        if not source_placeholders:
            return translation

        placeholder_matches = cls._iter_placeholder_matches(translation)
        placeholder_tokens = {token for _start, _end, token in placeholder_matches}
        if not placeholder_tokens.issubset(source_placeholders):
            return None

        translation_highlights = (
            []
            if unit is None
            else cls._iter_translation_highlights(
                translation, unit, placeholder_matches
            )
        )
        if len(placeholder_matches) + len(translation_highlights) != len(
            source_placeholders
        ):
            repaired = cls._repair_duplicate_placeholder(
                translation,
                source_text,
                unit,
                placeholder_matches,
                translation_highlights,
            )
            if repaired is None:
                return None
            translation = repaired
            placeholder_matches = cls._iter_placeholder_matches(translation)
            placeholder_tokens = {token for _start, _end, token in placeholder_matches}
            if not placeholder_tokens.issubset(source_placeholders):
                return None
            if unit is None:
                return None
            translation_highlights = cls._iter_translation_highlights(
                translation, unit, placeholder_matches
            )
            if len(placeholder_matches) + len(translation_highlights) != len(
                source_placeholders
            ):
                return None
        if not translation_highlights:
            return translation

        source_specs = cls._iter_source_placeholder_specs(source_text, unit)
        if source_specs is None:
            return None

        remaining_source_specs = [
            (token, highlight_text)
            for token, highlight_text in source_specs
            if token not in placeholder_tokens
        ]
        tokens_by_highlight_text: defaultdict[str, list[str]] = defaultdict(list)
        for token, highlight_text in remaining_source_specs:
            tokens_by_highlight_text[highlight_text].append(token)

        highlight_replacements: list[tuple[int, int, str]] = []
        for start, end, highlight_text in translation_highlights:
            tokens = tokens_by_highlight_text.get(highlight_text)
            if not tokens:
                return None
            highlight_replacements.append((start, end, tokens.pop(0)))

        replacements = [
            *placeholder_matches,
            *highlight_replacements,
        ]
        replacements.sort(key=itemgetter(0))

        result: list[str] = []
        current = 0
        for start, end, token in replacements:
            result.extend((translation[current:start], token))
            current = end
        result.append(translation[current:])
        return "".join(result)

    @classmethod
    def _repair_duplicate_placeholder(
        cls,
        translation: str,
        source_text: str,
        unit: Unit | None,
        placeholder_matches: list[tuple[int, int, str]],
        translation_highlights: list[tuple[int, int, str]],
    ) -> str | None:
        if unit is None:
            return None

        source_specs = cls._iter_source_placeholder_specs(source_text, unit)
        if source_specs is None:
            return None

        source_tokens = [token for token, _highlight_text in source_specs]
        actual_counts = cls._extract_placeholders(translation)
        expected_counts = Counter(source_tokens)
        extras = actual_counts - expected_counts
        missing = expected_counts - actual_counts
        if sum(extras.values()) != 1 or sum(missing.values()) > 1:
            return None

        extra_token = next(iter(extras))
        source_highlights = dict(source_specs)
        if extra_token not in source_highlights:
            return None
        extra_index = source_tokens.index(extra_token)
        missing_token = next(iter(missing), None)
        if missing_token is not None:
            if source_highlights.get(extra_token) != source_highlights.get(
                missing_token
            ):
                return None

            missing_index = source_tokens.index(missing_token)
            if missing_index >= extra_index:
                return None

        matches_by_token = [
            (start, end)
            for start, end, token in placeholder_matches
            if token == extra_token
        ]
        if len(matches_by_token) != expected_counts[extra_token] + 1:
            return None

        highlight_starts = [start for start, _end, _text in translation_highlights]
        candidates = [
            (start, end)
            for start, end in matches_by_token
            if any(
                start <= highlight_start < end for highlight_start in highlight_starts
            )
        ]
        if missing_token is not None:
            if len(candidates) != 1:
                return None

            start, end = candidates[0]
            return f"{translation[:start]}{missing_token}{translation[end:]}"

        if extra_index == 0:
            return None
        opening_token = source_tokens[extra_index - 1]
        if source_highlights.get(opening_token) == source_highlights.get(extra_token):
            return None

        opening_matches = [
            (start, end)
            for start, end, token in placeholder_matches
            if token == opening_token
        ]
        if len(opening_matches) != expected_counts[opening_token]:
            return None

        opening_end = opening_matches[-1][1]
        closing_candidates = [
            (start, end) for start, end in matches_by_token if start > opening_end
        ]
        if len(closing_candidates) != 2:
            return None

        start, end = closing_candidates[0]
        return f"{translation[:start]}{translation[end:]}"

    @classmethod
    def _placeholderize_existing_translation(
        cls, translation: str, source_text: str, unit: Unit | None
    ) -> str | None:
        return cls._placeholderize_translation(translation, source_text, unit)

    @classmethod
    def _placeholderize_assistant_reply(
        cls, translation: str, source_text: str, unit: Unit | None
    ) -> str:
        placeholderized = cls._placeholderize_translation(
            translation, source_text, unit
        )
        if placeholderized is None:
            msg = "Mismatching assistant reply."
            raise MachineTranslationError(msg)
        return placeholderized

    @classmethod
    def _is_string_list(
        cls, value: JSONValue, expected_length: int
    ) -> TypeGuard[list[str]]:
        return (
            isinstance(value, list)
            and len(value) == expected_length
            and all(isinstance(item, str) for item in value)
        )

    @classmethod
    def _normalize_translations(
        cls, translations: JSONValue, expected_length: int
    ) -> JSONValue:
        if (
            isinstance(translations, list)
            and len(translations) > expected_length
            and all(isinstance(item, str) for item in translations)
            and not any(translations[expected_length:])
        ):
            return translations[:expected_length]
        return translations

    @classmethod
    def _validate_translations(
        cls,
        translations: JSONValue,
        sources: list[tuple[str, Unit | None]],
    ) -> list[str]:
        translations = cls._normalize_translations(translations, len(sources))
        if not cls._is_string_list(translations, len(sources)):
            msg = "Mismatching assistant reply."
            raise MachineTranslationError(msg)

        normalized_translations: list[str] = []
        for index, translation in enumerate(translations):
            source_text = sources[index][0]
            normalized_translation = cls._placeholderize_assistant_reply(
                translation,
                source_text,
                sources[index][1],
            )
            if cls._extract_placeholders(
                normalized_translation
            ) != cls._extract_placeholders(source_text):
                msg = "Mismatching assistant reply."
                raise MachineTranslationError(msg)
            if cls._extract_literal_at_suffixes(
                normalized_translation
            ) != cls._extract_literal_at_suffixes(source_text):
                msg = "Mismatching assistant reply."
                raise MachineTranslationError(msg)
            normalized_translations.append(normalized_translation)

        return normalized_translations

    def download_multiple_translations(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> DownloadMultipleTranslations:
        return self._download_multiple_translations(
            source_language, target_language, sources, user, threshold
        )

    def download_pending_translations(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None, int]],
        user=None,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> DownloadMultipleTranslations:
        return self._download_multiple_translations(
            source_language,
            target_language,
            [(text, unit) for text, unit, _occurrence in sources],
            user,
            threshold,
            source_occurrences=[
                source_occurrence for _text, _unit, source_occurrence in sources
            ],
        )

    def _download_multiple_translations(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
        *,
        source_occurrences: list[int] | None = None,
    ) -> DownloadMultipleTranslations:
        started_cache = self._ensure_secondary_context_cache()
        try:
            return self._download_multiple_translations_with_context_cache(
                source_language,
                target_language,
                sources,
                user,
                threshold,
                source_occurrences=source_occurrences,
            )
        finally:
            self._clear_secondary_context_cache(started_cache)

    def _download_multiple_translations_with_context_cache(
        self,
        source_language,
        target_language,
        sources: list[tuple[str, Unit | None]],
        user=None,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
        *,
        source_occurrences: list[int] | None = None,
    ) -> DownloadMultipleTranslations:
        result: DownloadMultipleTranslations = defaultdict(list)

        prompt = self._get_prompt(target_language)
        content = self._get_message(
            source_language, target_language, sources, source_occurrences
        )
        previous_content, previous_response = self._get_previous_messages(
            source_language, target_language, sources
        )
        add_breadcrumb(self.name, "prompt", prompt=prompt)
        add_breadcrumb(self.name, "chat", content=content)

        translations_string = self.fetch_llm_translations(
            prompt, content, previous_content, previous_response
        )

        add_breadcrumb(self.name, "response", translations_string=translations_string)
        if translations_string is None or not translations_string:
            msg = "Blank assistant reply"
            self.log_handled_error(msg, extra_log=translations_string)
            raise MachineTranslationError(msg)

        try:
            translations = json.loads(translations_string)
        except json.JSONDecodeError as error:
            repaired_translations_string = self._repair_json_string_array(
                translations_string
            )
            if repaired_translations_string is None:
                msg = "Could not parse assistant reply as JSON."
                self.log_handled_error(msg, extra_log=translations_string)
                raise MachineTranslationError(msg) from error

            try:
                translations = json.loads(repaired_translations_string)
            except json.JSONDecodeError as repaired_error:
                msg = "Could not parse assistant reply as JSON."
                self.log_handled_error(msg, extra_log=translations_string)
                raise MachineTranslationError(msg) from repaired_error

            add_breadcrumb(self.name, "response-repaired")

        try:
            translations = self._validate_translations(translations, sources)
        except MachineTranslationError as error:
            msg = "Mismatching assistant reply."
            self.log_handled_error(msg, extra_log=translations_string)
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
