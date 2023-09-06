# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
from itertools import chain

import ahocorasick_rs
import sentry_sdk
from django.db.models import Q
from django.db.models.functions import Lower

from weblate.trans.models.unit import Unit
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.state import STATE_TRANSLATED

SPLIT_RE = re.compile(r"[\s,.:!?]+", re.UNICODE)
NON_WORD_RE = re.compile(r"\W", re.UNICODE)


def get_glossary_sources(component):
    # Fetch list of terms defined in a translation
    return list(
        set(
            component.source_translation.unit_set.filter(
                state__gte=STATE_TRANSLATED
            ).values_list(Lower("source"), flat=True)
        )
    )


def get_glossary_automaton(project):
    with sentry_sdk.start_span(op="glossary.automaton", description=project.slug):
        # Chain terms
        terms = set(
            chain.from_iterable(
                glossary.glossary_sources for glossary in project.glossaries
            )
        )
        # Build automaton for efficient Aho-Corasick search
        return ahocorasick_rs.AhoCorasick(
            terms,
            implementation=ahocorasick_rs.Implementation.ContiguousNFA,
            store_patterns=False,
        )


def get_glossary_terms(unit):
    """Return list of term pairs for an unit."""
    if unit.glossary_terms is not None:
        return unit.glossary_terms
    translation = unit.translation
    language = translation.language
    component = translation.component
    project = component.project
    source_language = component.source_language

    if language == source_language:
        return Unit.objects.none()

    units = (
        Unit.objects.prefetch()
        .filter(
            translation__component__in=project.glossaries,
            translation__component__source_language=source_language,
            translation__language=language,
        )
        .select_related("source_unit", "variant")
    )

    # Build complete source for matching
    parts = []
    for text in unit.get_source_plurals():
        text = text.lower().strip()
        if text:
            parts.append(text)
    source = PLURAL_SEPARATOR.join(parts)

    uses_ngram = source_language.uses_ngram()

    terms = set()
    automaton = project.glossary_automaton
    # Extract terms present in the source
    with sentry_sdk.start_span(op="glossary.match", description=project.slug):
        for _termno, start, end in automaton.find_matches_as_indexes(
            source, overlapping=True
        ):
            if uses_ngram or (
                (start == 0 or NON_WORD_RE.match(source[start - 1]))
                and (end >= len(source) or NON_WORD_RE.match(source[end]))
            ):
                terms.add(source[start:end].lower())

    units = list(
        units.annotate(source_lc=Lower("source")).filter(Q(source_lc__in=terms))
    )

    # Add variants manually. This could be done by adding filtering on
    # variant__unit__source in the above query, but this slows down the query
    # considerably and variants are rarely used.
    existing = {unit.pk for unit in units}
    variants = set()
    extra = []
    for unit in units:
        if unit.variant:
            if unit.variant.pk in variants:
                continue
            variants.add(unit.variant.pk)
            for child in unit.variant.unit_set.filter(translation__language=language):
                if child.pk not in existing:
                    existing.add(child.pk)
                    extra.append(child)

    units.extend(extra)

    # Order results, this is Python reimplementation of:
    units.sort(key=lambda x: x.glossary_sort_key)

    # Store in a unit cache
    unit.glossary_terms = units

    return units
