# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import OrderedDict, defaultdict
from copy import copy
from itertools import chain
from threading import Lock
from typing import TYPE_CHECKING, cast

import ahocorasick_rs
from django.core.cache import cache
from django.db.models import Prefetch, Q

from weblate.checks.flags import Flags
from weblate.trans.models.unit import Unit
from weblate.trans.util import split_plural
from weblate.utils.csv import PROHIBITED_INITIAL_CHARS
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.terminology import term_forbidden, term_records
from weblate.utils.tracing import start_span
from weblate.utils.unicodechars import CONTROLCHARS

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from weblate.trans.models import Project, Translation
    from weblate.utils.terminology import TermRecord

SPLIT_RE = re.compile(r"[\s,.:!?]+")
NON_WORD_RE = re.compile(r"\W")
PROHIBITED_INITIAL_CHARS_RE = re.compile(
    f"^({'|'.join(re.escape(char) for char in PROHIBITED_INITIAL_CHARS)})*"
)
CONTROLCHARS_TRANS = str.maketrans(dict.fromkeys(CONTROLCHARS))
GLOSSARY_AUTOMATON_CACHE_SIZE = 16
GLOSSARY_AUTOMATON_CACHE: OrderedDict[tuple[int, int], ahocorasick_rs.AhoCorasick] = (
    OrderedDict()
)
GLOSSARY_AUTOMATON_CACHE_LOCK = Lock()


def cleanup_glossary_term(text: str) -> str:
    """
    Clean up the provided glossary term by removing unwanted characters.

    - Translates and removes control characters.
    - Strips leading and trailing whitespace.
    - Removes prohibited leading characters.
    """
    text = text.translate(CONTROLCHARS_TRANS)
    return PROHIBITED_INITIAL_CHARS_RE.sub("", text).strip()


def get_glossary_source_index(component):
    result = defaultdict(list)
    for pk, source in component.source_translation.unit_set.filter(
        state__gte=STATE_TRANSLATED
    ).values_list("pk", "source"):
        for alias in dict.fromkeys(split_plural(source.lower())):
            if alias:
                result[alias].append(pk)
    return dict(result)


def get_glossary_sources(component):
    return list(component.glossary_source_index)


def clear_glossary_automaton_cache(project_id: int | None = None) -> None:
    """Clear process-local glossary automatons."""
    with GLOSSARY_AUTOMATON_CACHE_LOCK:
        if project_id is None:
            GLOSSARY_AUTOMATON_CACHE.clear()
        else:
            for cache_key in list(GLOSSARY_AUTOMATON_CACHE):
                if cache_key[0] == project_id:
                    del GLOSSARY_AUTOMATON_CACHE[cache_key]


def get_glossary_automaton(project: Project) -> ahocorasick_rs.AhoCorasick:
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.models.component import (
        prefetch_glossary_terms,
    )

    with start_span(op="glossary.automaton", name=project.slug):
        cache_key = (project.pk, project.glossary_automaton_cache_version)
        with GLOSSARY_AUTOMATON_CACHE_LOCK:
            if cache_key in GLOSSARY_AUTOMATON_CACHE:
                GLOSSARY_AUTOMATON_CACHE.move_to_end(cache_key)
                return GLOSSARY_AUTOMATON_CACHE[cache_key]

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
        result = ahocorasick_rs.AhoCorasick(
            terms,
            implementation=ahocorasick_rs.Implementation.ContiguousNFA,
            store_patterns=False,
        )
        with GLOSSARY_AUTOMATON_CACHE_LOCK:
            GLOSSARY_AUTOMATON_CACHE[cache_key] = result
            GLOSSARY_AUTOMATON_CACHE.move_to_end(cache_key)
            while len(GLOSSARY_AUTOMATON_CACHE) > GLOSSARY_AUTOMATON_CACHE_SIZE:
                GLOSSARY_AUTOMATON_CACHE.popitem(last=False)
        return result


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


def fetch_glossary_terms(  # ruff: ignore[complex-structure]
    units: list[Unit], *, full: bool = False, include_variants: bool = True
) -> None:
    """Fetch glossary terms for list of units."""
    from weblate.trans.models import (  # ruff: ignore[import-outside-top-level]
        Component,
        Project,
    )

    # ruff: ignore[import-outside-top-level]
    from weblate.workspaces.models import (
        Workspace,
    )

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
        # Do not get glossary matches when display is disabled
        if component.hide_glossary_matches:
            continue
        project = component.project
        source_language = component.source_language

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
        with start_span(op="glossary.match", name=project.slug):
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

            # Exclude currently edited unit items to prevent self-referencing glossary items
            current_unit_ids = [u.pk for u in translation_units[translation_id] if u.pk]
            if current_unit_ids:
                base_units = base_units.exclude(pk__in=current_unit_ids)

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
                    Prefetch(
                        "translation__component__project__workspace",
                        queryset=Workspace.objects.defer_huge(),
                    ),
                )

            source_ids = {
                pk
                for glossary in project.glossaries
                for term in terms
                for pk in glossary.glossary_source_index.get(term, ())
            }
            glossary_units = list(
                base_units.filter(
                    Q(source_unit_id__in=source_ids) | Q(pk__in=source_ids)
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
                for alias in dict.fromkeys(
                    record["text"].lower() for record in glossary_source_records(match)
                ):
                    glossary_lookup[alias].append(match)

            # Inject matches back to the units
            for i, unit in enumerate(translation_units[translation_id]):
                result: dict[int, Unit] = {}
                for term, glossary_positions in positions[i].items():
                    try:
                        matches = glossary_lookup[term]
                    except KeyError:
                        continue

                    for match in matches:
                        item = result.setdefault(match.pk, copy(match))
                        item.glossary_positions = tuple(
                            sorted(
                                set(
                                    getattr(item, "glossary_positions", ())
                                    + tuple(glossary_positions)
                                )
                            )
                        )
                        item.matched_sources = tuple(
                            dict.fromkeys((*(item.matched_sources or ()), term))
                        )
                        for variant in glossary_variants[match.pk].values():
                            item = copy(variant)
                            item.glossary_positions = tuple(glossary_positions)
                            result[item.pk] = item

                for item in result.values():
                    prepare_glossary_alternatives(item)
                # Store sorted results in a unit cache
                unit.glossary_terms = sorted(
                    result.values(), key=lambda x: x.glossary_sort_key
                )


def glossary_source_records(unit: Unit) -> list[TermRecord]:
    """Use shared TBX source alternatives even before sibling files are reparsed."""
    if unit.details.get("tbx_terms") and unit.source_unit_id:
        return term_records(unit.source_unit, source=True)
    return term_records(unit, source=True)


def prepare_glossary_alternatives(unit):
    """Prepare a single concept row with independently selectable alternatives."""
    sources = glossary_source_records(unit)
    matched = getattr(unit, "matched_sources", None)
    if matched is not None:
        sources = [record for record in sources if record["text"].lower() in matched]
    # Shared notes occur on every term record; render them once at their scope.
    unit.glossary_notes = {"concept": [], "source": [], "target": []}
    term_note_lines = {
        line
        for record in sources
        for note in record.get("notes", [])
        if note.get("scope", "term") == "term"
        for line in note["text"].splitlines()
    }
    unit.glossary_note = "\n".join(
        line for line in unit.note.splitlines() if line not in term_note_lines
    )
    common_notes = {unit.glossary_note, unit.explanation, unit.source_unit.explanation}
    for side in ("source", "target"):
        records = (
            glossary_source_records(unit) if side == "source" else term_records(unit)
        )
        for record in records:
            for note in record.get("notes", []):
                scope = note.get("scope", "term")
                if scope == "term":
                    continue
                notes = unit.glossary_notes["concept" if scope == "concept" else side]
                already_rendered = any(
                    f"\n{note['text']}\n" in f"\n{text}\n" for text in common_notes
                )
                if note["text"] not in notes and not already_rendered:
                    notes.append(note["text"])
    unit.glossary_sources = sources
    readonly = "read-only" in unit.all_flags
    unit.glossary_target_language = (
        unit.translation.component.source_language
        if readonly
        else unit.translation.language
    )
    targets = sources if readonly else term_records(unit)
    forbidden = "forbidden" in unit.all_flags or all(
        term_forbidden(record) for record in sources
    )
    unit.glossary_targets = [
        dict(record, forbidden=forbidden or term_forbidden(record))
        for record in targets
        if record["text"]
    ]


def iter_glossary_alternatives(units):
    """Adapt concept alternatives for scalar glossary consumers and copy actions."""
    for unit in units:
        sources = glossary_source_records(unit)
        matched = getattr(unit, "matched_sources", None)
        if matched is not None:
            sources = [
                record for record in sources if record["text"].lower() in matched
            ]
        readonly = "read-only" in unit.all_flags
        for source in sources:
            for target in [source] if readonly else term_records(unit):
                item = copy(unit)
                item.source = source["text"]
                item.target = target["text"]
                item.all_flags = Flags(unit.all_flags)
                if term_forbidden(source) or term_forbidden(target):
                    item.all_flags.merge("forbidden")
                records = [source] if readonly else [source, target]
                notes = [
                    note["text"]
                    for record in records
                    for note in record.get("notes", [])
                    if note.get("text")
                ]
                item.note = "\n".join(dict.fromkeys(filter(None, [unit.note, *notes])))
                yield item


def get_glossary_tuples(units: Iterable[Unit]) -> Generator[tuple[str, str]]:
    r"""
    Build a glossary content as word tuples.

    Based on the DeepL specification:

    - duplicate source entries are not allowed
    - neither source nor target entry may be empty
    - source and target entries must not contain any C0 or C1 control characters (including, e.g., "\t" or "\n") or any Unicode newline
    - source and target entries must not contain any leading or trailing Unicode whitespace character
    - source/target entry pairs are separated by a newline
    - source entries and target entries are separated by a tab
    """
    from weblate.trans.models import (  # ruff: ignore[import-outside-top-level]
        Component,
        Project,
    )

    # ruff: ignore[import-outside-top-level]
    from weblate.workspaces.models import (
        Workspace,
    )

    # We can get list or iterator as well
    if hasattr(units, "prefetch_related"):
        units = units.prefetch_related(
            "source_unit",
            "translation",
            Prefetch("translation__component", queryset=Component.objects.defer_huge()),
            Prefetch(
                "translation__component__project",
                queryset=Project.objects.defer_huge(),
            ),
            Prefetch(
                "translation__component__project__workspace",
                queryset=Workspace.objects.defer_huge(),
            ),
        )

    included = set()
    for unit in iter_glossary_alternatives(units):
        # Skip forbidden term
        if "forbidden" in unit.all_flags:
            continue

        if not unit.translated and "read-only" not in unit.all_flags:
            continue

        # Cleanup strings
        source = cleanup_glossary_term(unit.source)
        target = (
            source
            if "read-only" in unit.all_flags
            else cleanup_glossary_term(unit.target)
        )

        # Skip blanks and duplicates
        if not source or not target or source in included:
            continue

        # Memoize included
        included.add(source)

        # Render TSV
        yield source, target


def render_glossary_units_tsv(units: Iterable[Unit]) -> str:
    """Build a tab separated glossary."""
    return "\n".join(
        f"{source}\t{target}" for source, target in get_glossary_tuples(units)
    )


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
