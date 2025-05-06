# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from functools import reduce
from typing import TYPE_CHECKING, Literal

from django.db.models import Count, Prefetch, Q, Value
from django.db.models.functions import MD5, Lower
from django.utils.translation import gettext, gettext_lazy, ngettext

from weblate.checks.base import BatchCheckMixin, TargetCheck
from weblate.trans.actions import ActionEvents
from weblate.utils.html import format_html_join_comma
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.trans.models import Component, Unit


class PluralsCheck(TargetCheck):
    """Check for incomplete plural forms."""

    check_id = "plurals"
    name = gettext_lazy("Missing plurals")
    description = gettext_lazy("Some plural forms are untranslated.")

    def should_skip(self, unit: Unit):
        if unit.translation.component.is_multivalue:
            return True
        return super().should_skip(unit)

    def check_target_unit(self, sources: list[str], targets: list[str], unit: Unit):
        # Is this plural?
        if len(sources) == 1:
            return False
        # Is at least something translated?
        if targets == len(targets) * [""]:
            return False
        # Check for empty translation
        return "" in targets

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Target strings are checked in check_target_unit."""
        return False


class SamePluralsCheck(TargetCheck):
    """Check for same plural forms."""

    check_id = "same-plurals"
    name = gettext_lazy("Same plurals")
    description = gettext_lazy("Some plural forms are translated in the same way.")

    def check_target_unit(self, sources: list[str], targets: list[str], unit: Unit):
        # Is this plural?
        if len(sources) == 1 or len(targets) == 1:
            return False
        if not targets[0]:
            return False
        return len(set(targets)) == 1

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Target strings are checked in check_target_unit."""
        return False


class ConsistencyCheck(TargetCheck, BatchCheckMixin):
    """Check for inconsistent translations."""

    check_id = "inconsistent"
    name = gettext_lazy("Inconsistent")
    description = gettext_lazy(
        "This string has more than one translation in this project "
        "or is untranslated in some components."
    )
    ignore_untranslated = False
    propagates = "source"
    batch_project_wide = True
    skip_suggestions = True

    def check_target_unit(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> bool:
        component = unit.translation.component
        if not component.allow_translation_propagation:
            return False

        # Use last result if checks are batched
        if component.batch_checks:
            return self.handle_batch(unit, component)

        others = unit.propagated_units.exclude(target=unit.target)
        if not unit.translated:
            # Look only for translated units
            others = others.filter(state__gte=STATE_TRANSLATED)
        return others.exists()

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Target strings are checked in check_target_unit."""
        return False

    def check_component(self, component: Component) -> Iterable[Unit]:
        from weblate.trans.models import Unit

        units = Unit.objects.filter(
            translation__component__project=component.project,
            translation__component__allow_translation_propagation=True,
        )

        # List strings with different targets
        # Limit this to 100 strings, otherwise the resulting query is way too complex
        matches = (
            units.values("id_hash", "translation__plural_id")
            .annotate(Count("target", distinct=True))
            .filter(target__count__gt=1)
            .order_by("id_hash")[:100]
        )

        if not matches:
            return []

        return (
            units.filter(
                reduce(
                    lambda x, y: x
                    | (
                        Q(id_hash=y["id_hash"])
                        & Q(translation__plural_id=y["translation__plural_id"])
                    ),
                    matches,
                    Q(),
                )
            )
            .prefetch()
            .prefetch_bulk()
        )


class ReusedCheck(TargetCheck, BatchCheckMixin):
    """
    Check for reused translations.

    This is skipped for languages with a single plural form as that causes too
    many false positives, see https://github.com/WeblateOrg/weblate/issues/9450
    """

    check_id = "reused"
    name = gettext_lazy("Reused translation")
    description = gettext_lazy("Different strings are translated the same.")
    propagates = "target"
    batch_project_wide = True
    skip_suggestions = True

    def should_skip(self, unit: Unit):
        if unit.translation.plural.number <= 1 or not any(unit.get_target_plurals()):
            return True
        return super().should_skip(unit)

    def check_target_unit(self, sources: list[str], targets: list[str], unit: Unit):
        from weblate.trans.models import Unit

        translation = unit.translation
        component = translation.component

        # Use last result if checks are batched
        if component.batch_checks:
            return self.handle_batch(unit, component)

        return Unit.objects.same_target(unit).exists()

    def get_description(self, check_obj):
        from weblate.trans.models import Unit

        other_sources = (
            Unit.objects.same_target(check_obj.unit)
            .values_list("source", flat=True)
            .distinct()
        )

        return ngettext(
            "Other source string: %s", "Other source strings: %s", len(other_sources)
        ) % format_html_join_comma(
            "{}", ((gettext("“%s”") % source,) for source in other_sources)
        )

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Target strings are checked in check_target_unit."""
        return False

    def check_component(self, component: Component) -> Iterable[Unit]:
        from weblate.trans.models import Unit

        units = Unit.objects.filter(
            translation__component__project=component.project,
            translation__component__allow_translation_propagation=True,
            state__gte=STATE_TRANSLATED,
        )
        # Lower has no effect here, but we want to utilize index
        units = units.exclude(target__lower__md5=MD5(Value("")))

        # List strings with different sources
        # Limit this to 20 strings, otherwise the resulting query is too slow
        # Use ordering to make the limit deterministic
        matches = (
            units.values("target", "translation__plural_id")
            .annotate(source__count=Count("source", distinct=True))
            .filter(source__count__gt=1)
            .order_by("target__lower__md5")[:20]
        )

        if not matches:
            return

        result = (
            units.filter(
                reduce(
                    lambda x, y: x
                    | (
                        Q(target__lower__md5=MD5(Lower(Value(y["target"]))))
                        & Q(target=y["target"])
                        & Q(translation__plural_id=y["translation__plural_id"])
                    ),
                    matches,
                    Q(),
                )
            )
            .prefetch()
            .prefetch_bulk()
        )

        # Filter out case differing source for case insensitive languages
        found: dict[tuple[str, str], set[str]] = defaultdict(set)
        remaining: list[tuple[str, Unit]] = []
        for unit in result:
            if not unit.translation.language.is_case_sensitive():
                key = (unit.translation.language.code, unit.target)
                lower_source = unit.source.lower()
                found[key].add(lower_source)
                remaining.append((key, unit))
            else:
                yield unit

        for key, unit in remaining:
            if len(found[key]) > 1:
                yield unit


class TranslatedCheck(TargetCheck, BatchCheckMixin):
    """Check for inconsistent translations."""

    check_id = "translated"
    name = gettext_lazy("Has been translated")
    description = gettext_lazy("This string has been translated in the past.")
    ignore_untranslated = False
    skip_suggestions = True

    def get_description(self, check_obj):
        unit = check_obj.unit
        target = self.check_target_unit(unit.source, unit.target, unit)
        if not target:
            return super().get_description(check_obj)
        return gettext('Previous translation was "%s".') % target

    def should_skip_change(self, change, unit: Unit):
        # Skip automatic translation entries adding needs editing string
        return (
            change.action == ActionEvents.AUTO
            and change.details.get("state", STATE_TRANSLATED) < STATE_TRANSLATED
        )

    @staticmethod
    def should_break_changes(change):
        # Stop changes processing on source string change or on
        # intentional marking as needing edit
        return change.action in {
            ActionEvents.SOURCE_CHANGE,
            ActionEvents.MARKED_EDIT,
        }

    def check_target_unit(  # type: ignore[override]
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> Literal[False] | str:
        # TODO: this is type annotation hack, instead the check should have a proper return type
        if unit.translated:
            return False

        component = unit.translation.component

        if component.batch_checks:
            if self.handle_batch(unit, component):
                # This needs to be true-ish value
                return "present"
            return False

        from weblate.trans.models import Change

        changes = unit.change_set.filter(action__in=Change.ACTIONS_CONTENT).order()

        for change in changes:
            if self.should_break_changes(change):
                break
            if self.should_skip_change(change, unit):
                continue
            if change.target and change.target != unit.target:
                return change.target

        return False

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Target strings are checked in check_target_unit."""
        return False

    def get_fixup(self, unit: Unit):
        target = self.check_target_unit(
            unit.get_source_plurals(), unit.get_target_plurals(), unit
        )
        if not target:
            return None
        return [(".*", target, "u")]

    def check_component(self, component: Component) -> Iterable[Unit]:
        from weblate.trans.models import Change, Unit

        units = (
            Unit.objects.filter(
                translation__component=component,
                change__action__in=Change.ACTIONS_CONTENT,
                state__lt=STATE_TRANSLATED,
            )
            .prefetch_related(
                Prefetch(
                    "change_set",
                    queryset=Change.objects.filter(
                        action__in=Change.ACTIONS_CONTENT,
                    ).order(),
                    to_attr="recent_consistency_changes",
                )
            )
            .prefetch()
            .prefetch_bulk()
        )

        for unit in units:
            for change in unit.recent_consistency_changes:
                if self.should_break_changes(change):
                    break
                if self.should_skip_change(change, unit):
                    continue
                if change.target:
                    yield unit
