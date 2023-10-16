# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import defaultdict
from itertools import chain

import ahocorasick_rs
import sentry_sdk
from django.db.models import Q, Value
from django.db.models.functions import MD5, Lower

from weblate.trans.models.unit import Unit
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.state import STATE_TRANSLATED

SPLIT_RE = re.compile(r"[\s,.:!?]+")
NON_WORD_RE = re.compile(r"\W")


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
            Unit.objects.prefetch()
            .filter(
                Q(source__lower__md5__in=[MD5(Value(term)) for term in positions]),
                translation__component__in=project.glossaries,
                translation__component__source_language=source_language,
                translation__language=language,
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
