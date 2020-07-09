#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import SourceCheck
from weblate.utils.state import STATE_EMPTY, STATE_FUZZY

# Matches (s) not followed by alphanumeric chars or at the end
PLURAL_MATCH = re.compile(r"\(s\)(\W|\Z)")


class OptionalPluralCheck(SourceCheck):
    """Check for not used plural form."""

    check_id = "optional_plural"
    name = _("Unpluralised")
    description = _("The string is used as plural, but not using plural forms")

    def check_source_unit(self, source, unit):
        if len(source) > 1:
            return False
        return len(PLURAL_MATCH.findall(source[0])) > 0


class EllipsisCheck(SourceCheck):
    """Check for using "..." instead of "…"."""

    check_id = "ellipsis"
    name = _("Ellipsis")
    description = _(
        "The string uses three dots (...) " "instead of an ellipsis character (…)"
    )

    def check_source_unit(self, source, unit):
        return "..." in source[0]


class MultipleFailingCheck(SourceCheck):
    """Check whether there are more failing checks on this translation."""

    check_id = "multiple_failures"
    name = _("Multiple failing checks")
    description = _("The translations in several languages have failing checks")

    def check_source_unit(self, source, unit):
        from weblate.checks.models import Check

        related = Check.objects.filter(
            unit__id_hash=unit.id_hash,
            unit__translation__component=unit.translation.component,
        ).exclude(unit_id=unit.id)
        return related.count() >= 2


class LongUntranslatedCheck(SourceCheck):
    check_id = "long_untranslated"
    name = _("Long untranslated")
    description = _("The string has not been translated for a long time")

    def check_source_unit(self, source, unit):
        from weblate.trans.models import Unit

        if unit.timestamp > timezone.now() - timedelta(days=90):
            return False
        states = list(
            Unit.objects.filter(
                translation__component=unit.translation.component, id_hash=unit.id_hash
            ).values_list("state", flat=True)
        )
        total = len(states)
        not_translated = states.count(STATE_EMPTY) + states.count(STATE_FUZZY)
        translated_percent = (total - not_translated) / total
        return (
            total
            and translated_percent < unit.translation.component.stats.translated_percent
        )
