# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from copy import copy
from itertools import chain
from typing import TYPE_CHECKING, cast

import ahocorasick_rs
import sentry_sdk
from django.core.cache import cache
from django.db.models import Prefetch, Q, Value
from django.db.models.functions import MD5, Lower

from weblate.trans.models.unit import Unit
from weblate.utils.csv import PROHIBITED_INITIAL_CHARS
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.trans.models.translation import Translation

SPLIT_RE = re.compile(r"[\s,.:!?]+")
NON_WORD_RE = re.compile(r"\W")
# All control chars including tab and newline, this is different from
# weblate.formats.helpers.CONTROLCHARS which contains only chars
# problematic in XML or SQL scopes.
CONTROLCHARS = [
    char
    for char in map(chr, range(sys.maxunicode + 1))
    if unicodedata.category(char) in {"Zl", "Cc"}
]
CONTROLCHARS_TRANS = str.maketrans(dict.fromkeys(CONTROLCHARS))


def get_glossary_sources(component):
    # Fetch list of terms defined in a translation
    return list(
        component.source_translation.unit_set.filter(state__gte=STATE_TRANSLATED)
        .values_list(Lower("source"), flat=True)
        .distinct()
    )


def get_glossary_automaton(project):
    from weblate.trans.models.component import prefetch_glossary_terms

    with sentry_sdk.start_span(op="glossary.automaton", name=project.slug):
        # Chain terms
        prefetch_glossary_terms(project.glossaries)
        terms = set(
            chain.from_iterable(
                glossary.glossary_sources for glossary in project.glossaries
            )
        )
        # Remove blank string as that is not really reasonable to match
        terms.discard("")
        # Build automaton for efficient Aho-Corasick search
        return ahocorasick_rs.AhoCorasick(
            terms,
            implementation=ahocorasick_rs.Implementation.ContiguousNFA,
            store_patterns=False,
        )


def get_glossary_units(project, source_language, target_language):
    return Unit.objects.filter(
        translation__component__in=project.glossaries,
        translation__component__source_language=source_language,
        translation__language=target_language,
    )


def get_glossary_terms(
    unit: Unit, *, full: bool = False, include_variants: bool = True
) -> list[Unit]:
    """Return list of term pairs for an unit."""
    if unit.glossary_terms is None:
        fetch_glossary_terms([unit], full=full, include_variants=include_variants)
    return cast("list[Unit]", unit.glossary_terms)


def fetch_glossary_terms(  # noqa: C901
    units: list[Unit], *, full: bool = False, include_variants: bool = True
) -> None:
    """Fetch glossary terms for list of units."""
    from weblate.trans.models import Component, Project

    if len(units) == 0:
        return

    translations: dict[int, Translation] = {}
    translation_units: dict[int, list[Unit]] = defaultdict(list)

    for unit in units:
        translations[unit.translation.id] = unit.translation
        translation_units[unit.translation.id].append(unit)
        # Initialize glossary terms
        unit.glossary_terms = []

    for translation_id, translation in translations.items():
        language = translation.language
        component = translation.component
        project = component.project
        source_language = component.source_language

        # Short circuit source language
        if language == source_language:
            continue

        # Extract all source strings
        sources = [unit.source.lower() for unit in translation_units[translation_id]]

        # Match word boundaries if needed
        uses_whitespace = source_language.uses_whitespace()
        boundaries: list[set[int]] = [set() for i in range(len(sources))]
        if uses_whitespace:
            # Get list of word boundaries
            for i, source in enumerate(sources):
                boundaries[i] = {
                    match.span()[0] for match in NON_WORD_RE.finditer(source)
                }
                boundaries[i].add(-1)
                boundaries[i].add(len(source))

        automaton = project.glossary_automaton
        positions: list[dict[str, list[tuple[int, int]]]] = [
            defaultdict(list) for i in range(len(sources))
        ]
        terms: set[str] = set()
        # Extract terms present in the source
        with sentry_sdk.start_span(op="glossary.match", name=project.slug):
            for i, source in enumerate(sources):
                for _termno, start, end in automaton.find_matches_as_indexes(
                    source, overlapping=True
                ):
                    if not uses_whitespace or (
                        (start - 1 in boundaries[i]) and (end in boundaries[i])
                    ):
                        term = source[start:end].lower()
                        terms.add(term)
                        positions[i][term].append((start, end))

            # Skip processing when there are no matches
            if not terms:
                continue

            base_units = get_glossary_units(project, source_language, language)
            # Variant is used for variant grouping below, source unit for flags
            base_units = base_units.select_related("source_unit", "variant")

            if full:
                # Include full details needed for rendering
                base_units = base_units.prefetch()
            else:
                # Component priority is needed for ordering, file format and flags for flags
                base_units = base_units.prefetch_related(
                    Prefetch(
                        "translation__component",
                        queryset=Component.objects.only(
                            "priority",
                            "file_format",
                            "check_flags",
                            "project",
                        ),
                    ),
                    Prefetch(
                        "translation__component__project",
                        queryset=Project.objects.only(
                            "check_flags",
                        ),
                    ),
                )

            glossary_units = list(
                base_units.filter(
                    Q(source__lower__md5__in=[MD5(Value(term)) for term in terms]),
                )
            )

            # Add variants manually. This could be done by adding filtering on
            # variant__unit__source in the above query, but this slows down the query
            # considerably and variants are rarely used.
            glossary_variants: dict[int, dict[int, Unit]] = defaultdict(dict)
            if include_variants:
                processed_variants = set()

                for match in glossary_units:
                    if not match.variant_id or match.variant_id in processed_variants:
                        continue
                    processed_variants.add(match.variant_id)
                    for child in base_units.filter(variant_id=match.variant_id).exclude(
                        pk=match.pk
                    ):
                        glossary_variants[match.pk][child.pk] = child

            # Prepare term lookup
            glossary_lookup: dict[str, list[Unit]] = defaultdict(list)
            for match in glossary_units:
                glossary_lookup[match.source.lower()].append(match)

            # Inject matches back to the units
            for i, unit in enumerate(translation_units[translation_id]):
                result: dict[int, Unit] = {}
                for term, glossary_positions in positions[i].items():
                    try:
                        matches = glossary_lookup[term]
                    except KeyError:
                        continue

                    for match in matches:
                        item = copy(match)
                        item.glossary_positions = tuple(glossary_positions)
                        result[item.pk] = item
                        for variant in glossary_variants[match.pk].values():
                            item = copy(variant)
                            item.glossary_positions = tuple(glossary_positions)
                            result[item.pk] = item

                # Store sorted results in a unit cache
                unit.glossary_terms = sorted(
                    result.values(), key=lambda x: x.glossary_sort_key
                )


def render_glossary_units_tsv(units) -> str:
    r"""
    Build a tab separated glossary.

    Based on the DeepL specification:

    - duplicate source entries are not allowed
    - neither source nor target entry may be empty
    - source and target entries must not contain any C0 or C1 control characters (including, e.g., "\t" or "\n") or any Unicode newline
    - source and target entries must not contain any leading or trailing Unicode whitespace character
    - source/target entry pairs are separated by a newline
    - source entries and target entries are separated by a tab
    """
    from weblate.trans.models.component import Component

    def cleanup(text):
        """
        Clean up the provided text by removing unwanted characters.

        - Translates and removes control characters using CONTROLCHARS_TRANS.
        - Strips leading and trailing whitespace.
        - Removes leading characters from PROHIBITED_INITIAL_CHARS if present.
        """
        text = text.translate(CONTROLCHARS_TRANS)
        prohibited_initial_chars_pattern = (
            "^("
            r"\s"
            "|" + "|".join(re.escape(char) for char in PROHIBITED_INITIAL_CHARS) + ")*"
        )

        return re.sub(prohibited_initial_chars_pattern, "", text).strip()

    # We can get list or iterator as well
    if hasattr(units, "prefetch_related"):
        units = units.prefetch_related(
            "source_unit",
            "translation",
            Prefetch("translation__component", queryset=Component.objects.defer_huge()),
        )

    included = set()
    output = []
    for unit in units:
        # Skip forbidden term
        if "forbidden" in unit.all_flags:
            continue

        if not unit.translated and "read-only" not in unit.all_flags:
            continue

        # Cleanup strings
        source = cleanup(unit.source)
        target = source if "read-only" in unit.all_flags else cleanup(unit.target)

        # Skip blanks and duplicates
        if not source or not target or source in included:
            continue

        # Memoize included
        included.add(source)

        # Render TSV
        output.append(f"{source}\t{target}")

    return "\n".join(output)


def get_glossary_tsv(translation) -> str:
    project = translation.component.project
    source_language = translation.component.source_language
    language = translation.language

    cache_key = project.get_glossary_tsv_cache_key(source_language, language)

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Get glossary units
    units = get_glossary_units(project, source_language, language)

    # Render as tsv
    result = render_glossary_units_tsv(units.filter(state__gte=STATE_TRANSLATED))

    cache.set(cache_key, result, 24 * 3600)

    return result
