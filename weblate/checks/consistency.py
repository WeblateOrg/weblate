# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from functools import reduce
from typing import TYPE_CHECKING, Literal

from django.db.models import Count, Prefetch, Q, Value
from django.db.models.functions import MD5, Lower
from django.utils.translation import gettext, gettext_lazy, ngettext

from weblate.checks.base import BatchCheckMixin, TargetCheck
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.trans.models import Component, Unit
    from weblate.trans.models.unit import UnitQuerySet


class PluralsCheck(TargetCheck):
    """Check for incomplete plural forms."""

    check_id = "plurals"
    name = gettext_lazy("Missing plurals")
    description = gettext_lazy("Some plural forms are untranslated")

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
    description = gettext_lazy("Some plural forms are translated in the same way")

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
    propagates = True
    batch_project_wide = True
    skip_suggestions = True

    def get_propagated_value(self, unit: Unit) -> None | str:
        return unit.target

    def get_propagated_units(
        self, unit: Unit, target: str | None = None
    ) -> UnitQuerySet:
        return unit.same_source_units

    def check_target_unit(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> bool:
        component = unit.translation.component
        if not component.allow_translation_propagation:
            return False

        # Use last result if checks are batched
        if component.batch_checks:
            return self.handle_batch(unit, component)

        for other in self.get_propagated_units(unit):
            if unit.target == other.target:
                continue
            if unit.translated or other.translated:
                return True
        return False

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Target strings are checked in check_target_unit."""
        return False

    def check_component(self, component: Component):
        from weblate.trans.models import Unit

        units = Unit.objects.filter(
            translation__component__project=component.project,
            translation__component__allow_translation_propagation=True,
        )

        # List strings with different targets
        # Limit this to 100 strings, otherwise the resulting query is way too complex
        matches = (
            units.values("id_hash", "translation__language", "translation__plural")
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
                        & Q(translation__language=y["translation__language"])
                        & Q(translation__plural=y["translation__plural"])
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
    propagates = True
    batch_project_wide = True
    skip_suggestions = True

    def get_propagated_value(self, unit: Unit):
        return unit.source

    def get_propagated_units(self, unit: Unit, target: str | None = None):
        from weblate.trans.models import Unit

        if target is None:
            return unit.same_target_units
        return Unit.objects.same_target(unit, target)

    def should_skip(self, unit: Unit):
        if unit.translation.plural.number <= 1 or not any(unit.get_target_plurals()):
            return True
        return super().should_skip(unit)

    def check_target_unit(self, sources: list[str], targets: list[str], unit: Unit):
        translation = unit.translation
        component = translation.component

        # Use last result if checks are batched
        if component.batch_checks:
            return self.handle_batch(unit, component)

        return self.get_propagated_units(unit).exists()

    def get_description(self, check_obj):
        other_sources = (
            self.get_propagated_units(check_obj.unit)
            .values_list("source", flat=True)
            .distinct()
        )

        return ngettext(
            "Other source string: %s", "Other source strings: %s", len(other_sources)
        ) % ", ".join(gettext("“%s”") % source for source in other_sources)

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Target strings are checked in check_target_unit."""
        return False

    def check_component(self, component: Component):
        from weblate.trans.models import Unit

        units = Unit.objects.filter(
            translation__component__project=component.project,
            translation__component__allow_translation_propagation=True,
            state__gte=STATE_TRANSLATED,
        )
        # Lower has no effect here, but we want to utilize index
        units = units.exclude(target__lower__md5=MD5(Lower(Value(""))))

        # List strings with different sources
        # Limit this to 20 strings, otherwise the resulting query is too slow
        matches = (
            units.values("target__md5", "translation__language", "translation__plural")
            .annotate(source__count=Count("source", distinct=True))
            .filter(source__count__gt=1)
            .order_by("target__md5")[:20]
        )

        if not matches:
            return []

        return (
            units.filter(
                reduce(
                    lambda x, y: x
                    | (
                        Q(target__md5=y["target__md5"])
                        & Q(translation__language=y["translation__language"])
                        & Q(translation__plural=y["translation__plural"])
                    ),
                    matches,
                    Q(),
                )
            )
            .prefetch()
            .prefetch_bulk()
        )


class TranslatedCheck(TargetCheck, BatchCheckMixin):
    """Check for inconsistent translations."""

    check_id = "translated"
    name = gettext_lazy("Has been translated")
    description = gettext_lazy("This string has been translated in the past")
    ignore_untranslated = False
    skip_suggestions = True

    def get_description(self, check_obj):
        unit = check_obj.unit
        target = self.check_target_unit(unit.source, unit.target, unit)
        if not target:
            return super().get_description(check_obj)
        return gettext('Previous translation was "%s".') % target

    def should_skip_change(self, change, unit: Unit):
        from weblate.trans.models import Change

        # Skip automatic translation entries adding needs editing string
        return (
            change.action == Change.ACTION_AUTO
            and change.details.get("state", STATE_TRANSLATED) < STATE_TRANSLATED
        )

    @staticmethod
    def should_break_changes(change):
        from weblate.trans.models import Change

        # Stop changes processing on source string change or on
        # intentional marking as needing edit
        return change.action in {Change.ACTION_SOURCE_CHANGE, Change.ACTION_MARKED_EDIT}

    def handle_batch(self, unit: Unit, component: Component) -> Literal[False] | str:  # type: ignore[override]
        # TODO: this is type annotation hack, instead the check should have a proper return type
        return super().handle_batch(unit, component)  # type: ignore[return-value]

    def check_target_unit(  # type: ignore[override]
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> Literal[False] | str:
        # TODO: this is type annotation hack, instead the check should have a proper return type
        if unit.translated:
            return False

        component = unit.translation.component

        if component.batch_checks:
            return self.handle_batch(unit, component)

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

    def check_component(self, component: Component):
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
