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
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext
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

    def get_related_checks(self, unit):
        from weblate.checks.models import Check

        return Check.objects.filter(unit__in=unit.unit_set.exclude(pk=unit.id))

    def check_source_unit(self, source, unit):
        related = self.get_related_checks(unit)
        return related.count() >= 2

    def get_description(self, check_obj):
        related = self.get_related_checks(check_obj.unit).select_related(
            "unit", "unit__translation", "unit__translation__language"
        )
        if not related:
            return super().get_description()

        checks = defaultdict(list)

        for check in related:
            checks[check.check].append(check)

        output = [gettext("Following checks are failing:")]
        for check_list in checks.values():
            output.append(
                "{}: {}".format(
                    check_list[0].get_name(),
                    ", ".join(
                        escape(str(check.unit.translation.language))
                        for check in check_list
                    ),
                )
            )

        return mark_safe("<br>".join(output))


class LongUntranslatedCheck(SourceCheck):
    check_id = "long_untranslated"
    name = _("Long untranslated")
    description = _("The string has not been translated for a long time")

    def check_source_unit(self, source, unit):
        if unit.timestamp > timezone.now() - timedelta(days=90):
            return False
        states = list(unit.unit_set.values_list("state", flat=True))
        total = len(states)
        not_translated = states.count(STATE_EMPTY) + states.count(STATE_FUZZY)
        translated_percent = 100 * (total - not_translated) / total
        return (
            total
            and 2 * translated_percent
            < unit.translation.component.stats.lazy_translated_percent
        )
