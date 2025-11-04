# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING

from django.db.models import Count, F, Q
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

        return Check.objects.filter(
            Q(unit_id__in=unit_ids) | Q(unit__source_unit_id__in=unit_ids)
        ).select_related("unit__translation")

    def check_source_unit(self, sources: list[str], unit: Unit):
        if unit.translation.component.batch_checks:
            return self.handle_batch(unit, unit.translation.component)
        return self._check_unit(unit)

    def _check_unit(self, unit: Unit) -> bool:
        related = (
            self.get_related_checks([unit.pk])
            .values_list("unit__translation", flat=True)
            .distinct()
        )
        return related.count() >= 2

    def check_component(self, component: Component) -> Iterable[Unit]:
        from weblate.trans.models import Unit

        unit_id_and_check_count = (
            self.get_related_checks(
                Unit.objects.filter(translation__component=component).values_list(
                    "pk", flat=True
                )
            )
            .values_list("unit__source_unit_id")
            .annotate(translation_count=Count("unit__translation_id", distinct=True))
            .filter(translation_count__gte=2)
        )
        return (
            Unit.objects.prefetch()
            .prefetch_bulk()
            .filter(
                id__in=unit_id_and_check_count.values_list(
                    "unit__source_unit_id", flat=True
                )
            )
        )

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
        component = unit.translation.component
        if component.batch_checks:
            return self.handle_batch(unit, component)
        return self._check_unit(unit)

    def _check_unit(self, unit: Unit) -> bool:
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

    def check_component(self, component: Component) -> Iterable[Unit]:
        from weblate.trans.models import Unit

        result = (
            Unit.objects.filter(
                translation__component=component,
                source_unit__timestamp__lt=timezone.now() - timedelta(days=90),
            )
            .values_list("source_unit_id")
            .annotate(
                total=Count("state"),
                not_translated=Count("state", filter=Q(state__lte=STATE_FUZZY)),
            )
            .filter(total__gt=0)
            .annotate(
                translated_percent=100 * (F("total") - F("not_translated")) / F("total")
            )
        ).filter(translated_percent__lt=component.stats.translated_percent / 2)
        return (
            Unit.objects.prefetch()
            .prefetch_bulk()
            .filter(id__in=result.values_list("source_unit_id", flat=True))
        )
