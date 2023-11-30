# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
from itertools import chain

import ahocorasick_rs
import sentry_sdk
from django.core.cache import cache
from django.db.models import Prefetch, Q, Value
from django.db.models.functions import MD5, Lower

from weblate.trans.models.unit import Unit
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.state import STATE_TRANSLATED

SPLIT_RE = re.compile(r"[\s,.:!?]+")
NON_WORD_RE = re.compile(r"\W")
# All control chars including tab and newline, this is dufferent from
# weblate.formats.helpers.CONTROLCHARS which contains only chars
# problematic in XML or SQL scopes.
CONTROLCHARS = [
    char
    for char in map(chr, range(sys.maxunicode + 1))
    if unicodedata.category(char) in ("Zl", "Cc")
]
CONTROLCHARS_TRANS = str.maketrans({char: None for char in CONTROLCHARS})


def get_glossary_sources(component):
    # Fetch list of terms defined in a translation
    return list(
        component.source_translation.unit_set.filter(state__gte=STATE_TRANSLATED)
        .values_list(Lower("source"), flat=True)
        .distinct()
    )


def get_glossary_automaton(project):
    from weblate.trans.models.component import prefetch_glossary_terms

    with sentry_sdk.start_span(op="glossary.automaton", description=project.slug):
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


def get_glossary_terms(unit: Unit) -> list[Unit]:
    """Return list of term pairs for an unit."""
    if unit.glossary_terms is not None:
        return unit.glossary_terms
    translation = unit.translation
    language = translation.language
    component = translation.component
    project = component.project
    source_language = component.source_language

    if language == source_language:
        return []

    # Build complete source for matching
    parts = []
    for text in unit.get_source_plurals():
        text = text.lower().strip()
        if text:
            parts.append(text)
    source = PLURAL_SEPARATOR.join(parts)

    uses_ngram = source_language.uses_ngram()

    automaton = project.glossary_automaton
    positions = defaultdict(list)
    # Extract terms present in the source
    with sentry_sdk.start_span(op="glossary.match", description=project.slug):
        for _termno, start, end in automaton.find_matches_as_indexes(
            source, overlapping=True
        ):
            if uses_ngram or (
                (start == 0 or NON_WORD_RE.match(source[start - 1]))
                and (end >= len(source) or NON_WORD_RE.match(source[end]))
            ):
                term = source[start:end].lower()
                positions[term].append((start, end))

        if not positions:
            unit.glossary_terms = []
            return []

        units = list(
            get_glossary_units(project, source_language, language)
            .prefetch()
            .filter(
                Q(source__lower__md5__in=[MD5(Value(term)) for term in positions]),
            )
            .select_related("source_unit", "variant")
        )

        # Add variants manually. This could be done by adding filtering on
        # variant__unit__source in the above query, but this slows down the query
        # considerably and variants are rarely used.
        existing = {unit.pk for unit in units}
        variants = set()
        extra = []
        for unit in units:
            if not unit.variant or unit.variant.pk in variants:
                continue
            variants.add(unit.variant.pk)
            for child in unit.variant.unit_set.filter(
                translation__language=language
            ).select_related("source_unit"):
                if child.pk not in existing:
                    existing.add(child.pk)
                    extra.append(child)

        units.extend(extra)

        # Order results, this is Python reimplementation of:
        units.sort(key=lambda x: x.glossary_sort_key)

        for unit in units:
            unit.glossary_positions = tuple(positions[unit.source.lower()])

    # Store in a unit cache
    unit.glossary_terms = units

    return units


def render_glossary_units_tsv(units) -> str:
    r"""
    Builds a tab separated glossary.

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
        return text.translate(CONTROLCHARS_TRANS).strip()

    included = set()
    output = []
    for unit in units.prefetch_related(
        "source_unit",
        "translation",
        Prefetch("translation__component", queryset=Component.objects.defer_huge()),
    ):
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
