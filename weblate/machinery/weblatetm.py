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

from functools import reduce
from typing import Set

from django.db.models import Q

from weblate.machinery.base import MachineTranslation, get_machinery_language
from weblate.trans.models import Unit
from weblate.utils.db import adjust_similarity_threshold
from weblate.utils.state import STATE_TRANSLATED


class WeblateTranslation(MachineTranslation):
    """Translation service using strings already translated in Weblate."""

    name = "Weblate"
    rank_boost = 1
    cache_translations = False
    accounting_key = "internal"
    do_cleanup = False

    def convert_language(self, language):
        """No conversion of language object."""
        return get_machinery_language(language)

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def is_rate_limited(self):
        """This service has no rate limiting."""
        return False

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        search: bool,
        threshold: int = 75,
    ):
        """Download list of possible translations from a service."""
        if user:
            base = Unit.objects.filter_access(user)
        else:
            base = Unit.objects.all()
        matching_units = base.filter(
            source__search=text,
            translation__component__source_language=source,
            translation__language=language,
            state__gte=STATE_TRANSLATED,
        ).prefetch()

        # We want only close matches here
        adjust_similarity_threshold(0.95)

        for munit in matching_units:
            source = munit.source_string
            if "forbidden" in munit.all_flags:
                continue
            quality = self.comparer.similarity(text, source)
            if quality < 10 or (quality < threshold and not search):
                continue
            yield {
                "text": munit.get_target_plurals()[0],
                "quality": quality,
                "service": self.name,
                "origin": str(munit.translation.component),
                "origin_url": munit.get_absolute_url(),
                "source": source,
            }

    def download_batch_strings(
        self, source, language, units, texts: Set[str], user=None, threshold: int = 75
    ):
        if user:
            base = Unit.objects.filter_access(user)
        else:
            base = Unit.objects.all()
        query = reduce(lambda x, y: x | Q(source__search=y), texts, Q())
        matching_units = base.filter(
            query,
            translation__component__source_language=source,
            translation__language=language,
            state__gte=STATE_TRANSLATED,
        ).only("source", "target")

        # We want only close matches here
        adjust_similarity_threshold(0.95)

        for unit in matching_units:
            yield unit.source_string, unit.get_target_plurals()[0]
