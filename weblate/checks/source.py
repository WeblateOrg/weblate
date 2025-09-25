# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import BatchCheckMixin, SourceCheck
from weblate.utils.html import format_html_join_comma
from weblate.utils.state import STATE_EMPTY, STATE_FUZZY

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.trans.models import Component, Unit

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


class MultipleFailingCheck(SourceCheck, BatchCheckMixin):
    """Check whether there are more failing checks on this translation."""

    check_id = "multiple_failures"
    name = gettext_lazy("Multiple failing checks")
    description = gettext_lazy(
        "The translations in several languages have failing checks."
    )

    def get_related_checks(self, unit_ids: Iterable[int]):
        from weblate.checks.models import Check

        return Check.objects.filter(unit_id__in=unit_ids).select_related(
            "unit__translation"
        )

    def check_source_unit(self, sources: list[str], unit: Unit):
        return self.handle_batch(unit, unit.translation.component)

    def check_component(self, component: Component) -> Iterable[Unit]:
        from weblate.trans.models import Unit

        pk_to_unit = {
            unit.pk: unit
            for unit in Unit.objects.filter(translation__component=component)
        }
        checks = self.get_related_checks(pk_to_unit.keys()).select_related(
            "unit__source_unit"
        )

        source_unit_to_translations = defaultdict(set)
        for check in checks:
            source_unit_to_translations[check.unit.source_unit.pk].add(
                check.unit.translation.pk
            )

        return [
            pk_to_unit[source_unit_pk]
            for source_unit_pk, translations in source_unit_to_translations.items()
            if len(translations) >= 2
        ]

    def get_description(self, check_obj):
        unit_ids = check_obj.unit.unit_set.exclude(pk=check_obj.unit.id).values_list(
            "pk", flat=True
        )
        related = self.get_related_checks(unit_ids).select_related(
            "unit__translation__language"
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


class LongUntranslatedCheck(SourceCheck, BatchCheckMixin):
    check_id = "long_untranslated"
    name = gettext_lazy("Long untranslated")
    description = gettext_lazy("The string has not been translated for a long time.")

    def check_source_unit(self, sources: list[str], unit: Unit) -> bool:
        return self.handle_batch(unit, unit.translation.component)

    def check_component(self, component: Component) -> Iterable[Unit]:
        from weblate.trans.models import Unit

        units = Unit.objects.filter(
            translation__component=component,
            source_unit__timestamp__lt=timezone.now() - timedelta(days=90),
        ).select_related("source_unit__translation__component")
        source_unit_to_states = defaultdict(list)
        source_units: set[Unit] = set()
        for unit in units:
            source_unit_to_states[unit.source_unit.pk].append(unit.state)
            source_units.add(unit.source_unit)

        result = []
        for unit in source_units:
            if states := source_unit_to_states[unit.pk]:
                total = len(states)
                not_translated = states.count(STATE_EMPTY) + states.count(STATE_FUZZY)
                translated_percent = 100 * (total - not_translated) / total
                if (
                    2 * translated_percent
                    < unit.translation.component.stats.translated_percent
                ):
                    result.append(unit)
        return result
