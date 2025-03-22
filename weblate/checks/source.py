# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import SourceCheck
from weblate.utils.html import format_html_join_comma
from weblate.utils.state import STATE_EMPTY, STATE_FUZZY

if TYPE_CHECKING:
    from weblate.trans.models import Unit

# Matches (s) not followed by alphanumeric chars or at the end
PLURAL_MATCH = re.compile(r"\w\(s\)(\W|\Z)")


class OptionalPluralCheck(SourceCheck):
    """Check for not used plural form."""

    check_id = "optional_plural"
    name = gettext_lazy("Unpluralised")
    description = gettext_lazy(
        "The string is used as plural, but not using plural forms."
    )

    def check_source_unit(self, sources: list[str], unit: Unit):
        if len(sources) > 1:
            return False
        return len(PLURAL_MATCH.findall(sources[0])) > 0


class EllipsisCheck(SourceCheck):
    """Check for using "..." instead of "…"."""

    check_id = "ellipsis"
    name = gettext_lazy("Ellipsis")
    description = gettext_lazy(
        "The string uses three dots (...) instead of an ellipsis character (…)."
    )

    def check_source_unit(self, sources: list[str], unit: Unit):
        return "..." in sources[0]


class MultipleFailingCheck(SourceCheck):
    """Check whether there are more failing checks on this translation."""

    check_id = "multiple_failures"
    name = gettext_lazy("Multiple failing checks")
    description = gettext_lazy(
        "The translations in several languages have failing checks."
    )

    def get_related_checks(self, unit: Unit):
        from weblate.checks.models import Check

        return Check.objects.filter(unit__in=unit.unit_set.exclude(pk=unit.id))

    def check_source_unit(self, sources: list[str], unit: Unit):
        related = (
            self.get_related_checks(unit)
            .values_list("unit__translation", flat=True)
            .distinct()
        )
        return related.count() >= 2

    def get_description(self, check_obj):
        related = self.get_related_checks(check_obj.unit).select_related(
            "unit", "unit__translation", "unit__translation__language"
        )
        if not related:
            return super().get_description(check_obj)

        checks = defaultdict(list)

        for check in related:
            checks[check.name].append(check)

        return format_html(
            "{}<dl>{}</dl>",
            gettext("Following checks are failing:"),
            format_html_join(
                "\n",
                "<dt>{}</dt><dd>{}</dd>",
                (
                    (
                        check_list[0].get_name(),
                        format_html_join_comma(
                            '<a href="{}">{}</a>',
                            (
                                (
                                    check.unit.get_absolute_url(),
                                    str(check.unit.translation.language),
                                )
                                for check in check_list
                            ),
                        ),
                    )
                    for check_list in checks.values()
                ),
            ),
        )


class LongUntranslatedCheck(SourceCheck):
    check_id = "long_untranslated"
    name = gettext_lazy("Long untranslated")
    description = gettext_lazy("The string has not been translated for a long time.")

    def check_source_unit(self, sources: list[str], unit: Unit):
        if unit.timestamp > timezone.now() - timedelta(days=90):
            return False
        states = list(unit.unit_set.values_list("state", flat=True))
        total = len(states)
        not_translated = states.count(STATE_EMPTY) + states.count(STATE_FUZZY)
        translated_percent = 100 * (total - not_translated) / total
        return (
            total
            and 2 * translated_percent
            < unit.translation.component.stats.translated_percent
        )
