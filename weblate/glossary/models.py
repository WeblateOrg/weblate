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
from functools import reduce
from itertools import islice

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from whoosh.analysis import LanguageAnalyzer, NgramAnalyzer, SimpleAnalyzer
from whoosh.analysis.filters import StopFilter
from whoosh.lang import NoStopWords

from weblate.checks.same import strip_string
from weblate.trans.models.unit import Unit
from weblate.utils.db import re_escape
from weblate.utils.errors import report_error

SPLIT_RE = re.compile(r"[\s,.:!?]+", re.UNICODE)


def get_glossary_terms(unit):
    """Return list of term pairs for an unit."""
    words = set()
    translation = unit.translation
    language = translation.language
    component = translation.component
    source_language = component.source_language

    units = (
        Unit.objects.prefetch()
        .filter(
            translation__component__in=component.project.glossaries,
            translation__component__source_language=source_language,
            translation__language=language,
        )
        .select_related("source_unit")
        .order_by(Lower("source"))
    )

    # Filters stop words for a language
    try:
        stopfilter = StopFilter(lang=source_language.base_code)
    except NoStopWords:
        stopfilter = StopFilter()

    # Prepare analyzers
    # - basic simple analyzer to split on non-word chars
    # - simple analyzer just splits words based on regexp to catch in word dashes
    # - language analyzer if available (it is for English)
    analyzers = [
        SimpleAnalyzer() | stopfilter,
        SimpleAnalyzer(expression=SPLIT_RE, gaps=True) | stopfilter,
        LanguageAnalyzer(source_language.base_code),
    ]

    # Add ngram analyzer for languages like Chinese or Japanese
    if source_language.uses_ngram():
        analyzers.append(NgramAnalyzer(4))

    # Extract words from all plurals and from context
    flags = unit.all_flags
    for text in unit.get_source_plurals() + [unit.context]:
        text = strip_string(text, flags).lower()
        for analyzer in analyzers:
            # Some Whoosh analyzers break on unicode
            try:
                words.update(token.text for token in analyzer(text))
            except (UnicodeDecodeError, IndexError):
                report_error(cause="Term words parsing")
            if len(words) > 1000:
                break
        if len(words) > 1000:
            break

    if "" in words:
        words.remove("")

    if not words:
        # No extracted words, no glossary
        return units.none()

    # Build the query for fetching the words
    # We want case insensitive lookup
    words = islice(words, 1000)
    if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
        # Use regex as that is utilizing pg_trgm index
        return units.filter(
            source__iregex=r"(^|[ \t\n\r\f\v])({})($|[ \t\n\r\f\v])".format(
                "|".join(re_escape(word) for word in words)
            ),
        )
    else:
        # MySQL
        return units.filter(
            reduce(
                lambda x, y: x | y,
                (models.Q(source__search=word) for word in words),
            ),
        )
