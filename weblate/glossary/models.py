#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import re
from itertools import chain

import ahocorasick
from django.db.models import Q
from django.db.models.functions import Lower

from weblate.trans.models.unit import Unit
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.db import re_escape, using_postgresql
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
    # Chain terms
    terms = set(
        chain.from_iterable(
            glossary.glossary_sources for glossary in project.glossaries
        )
    )
    # Build automaton for efficient Aho-Corasick search
    automaton = ahocorasick.Automaton()
    for term in terms:
        automaton.add_word(term, term)
    automaton.make_automaton()
    return automaton


def get_glossary_terms(unit):
    """Return list of term pairs for an unit."""
    if unit.glossary_terms is not None:
        return unit.glossary_terms
    translation = unit.translation
    language = translation.language
    component = translation.component
    project = component.project
    source_language = component.source_language

    units = (
        Unit.objects.prefetch().select_related("source_unit").order_by(Lower("source"))
    )
    if language == source_language:
        return units.none()

    # Build complete source for matching
    parts = [""]
    for text in unit.get_source_plurals() + [unit.context]:
        text = text.lower().strip()
        if text:
            parts.append(text)
    parts.append("")
    source = PLURAL_SEPARATOR.join(parts)

    uses_ngram = source_language.uses_ngram()

    matches = set()
    automaton = project.glossary_automaton
    if automaton.kind == ahocorasick.AHOCORASICK:

        # Extract terms present in the source
        for end, term in automaton.iter(source):
            if uses_ngram or (
                NON_WORD_RE.match(source[end - len(term)])
                and NON_WORD_RE.match(source[end + 1])
            ):
                matches.add(term)

    if using_postgresql():
        match = r"^({})$".format("|".join(re_escape(term) for term in matches))
        # Use regex as that is utilizing pg_trgm index
        query = Q(source__iregex=match) | Q(variant__unit__source__iregex=match)
    else:
        # With MySQL we utilize it does case insensitive lookup
        query = Q(source__in=matches) | Q(variant__unit__source__in=matches)

    units = units.filter(
        query,
        translation__component__in=project.glossaries,
        translation__component__source_language=source_language,
        translation__language=language,
    ).distinct()

    # Store in a unit cache
    unit.glossary_terms = units

    return units
