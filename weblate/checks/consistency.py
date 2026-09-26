# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from functools import reduce
from typing import TYPE_CHECKING, ClassVar, Literal

from django.db.models import Count, F, Max, Min, Prefetch, Q, Value
from django.db.models.functions import MD5, Lower
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy, ngettext

from weblate.checks.base import BatchCheckMixin, TargetCheck
from weblate.trans.actions import ACTIONS_REVERTABLE, ActionEvents
from weblate.trans.util import split_plural
from weblate.utils.html import format_html_join_comma
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.checks.models import Check
    from weblate.trans.models import Change, Component, Unit

    from .base import FixupType


class PluralsCheck(TargetCheck):
    """Check for incomplete plural forms."""

    check_id = "plurals"
    name = gettext_lazy("Missing plurals")
    description = gettext_lazy("Some plural forms are untranslated.")

    def should_skip(self, unit: Unit):
        if unit.translation.component.is_multivalue:
            return True
        return super().should_skip(unit)

    def check_target_unit(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> bool:
        # Required target forms are independent of the effective source's forms.
        if len(targets) <= 1:
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

    def check_target_unit(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> bool:
        if unit.has_multiple_values(sources, targets):
            return False
        # Is this plural?
        if len(sources) == 1 or len(targets) == 1:
            return False
        if not targets or not targets[0]:
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
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Translation, Unit

        custom_sources = bool(component.project.translation_parent_language_ids)
        translation_groups: dict[tuple[int, int | None], list[int]] = defaultdict(list)
        for translation_id, plural_id, source_language_id in Translation.objects.filter(
            component__project=component.project,
            component__allow_translation_propagation=True,
        ).values_list("id", "plural_id", "component__source_language_id"):
            # Effective source languages can vary within a translation. Canonical
            # languages can be partitioned here without joining the aggregate query.
            key = (plural_id, None if custom_sources else source_language_id)
            translation_groups[key].append(translation_id)

        fields = (
            ("check_source", "context", "check_source_language")
            if custom_sources
            else ("id_hash", "check_source_language")
        )
        ordering = (
            (*fields, "plural_id")
            if custom_sources
            else ("id_hash", "plural_id", "check_source_language")
        )
        # Aggregate each plural group separately to keep the aggregation state
        # smaller. Ordinary projects need no translation or component joins.
        queries = []
        for (
            plural_id,
            group_source_language_id,
        ), translation_ids in translation_groups.items():
            # Custom parents can give distinct canonical identities the same
            # source even within a single translation.
            if not custom_sources and len(translation_ids) < 2:
                continue
            units = Unit.objects.exclude_blocked(custom_sources=custom_sources).filter(
                translation_id__in=translation_ids
            )
            if custom_sources:
                units = units.with_effective_source()
            else:
                units = units.annotate(
                    check_source_language=Value(group_source_language_id)
                )
            queries.append(
                units.values(*fields)
                .annotate(
                    plural_id=Value(plural_id),
                    min_target=Min("target"),
                    max_target=Max("target"),
                )
                .filter(min_target__lt=F("max_target"))
                .order_by(*ordering)[:100]
            )

        if not queries:
            return []

        # A group's first 100 matches contain all its possible matches in the
        # global top 100. Keep that global limit and deterministic ordering.
        matches = queries[0]
        if len(queries) > 1:
            matches = matches.union(*queries[1:], all=True).order_by(*ordering)[:100]
        if not matches:
            return []

        query = Q()
        if custom_sources:
            for match in matches:
                query |= Q(
                    translation_id__in=translation_groups[match["plural_id"], None],
                    **{field: match[field] for field in fields},
                )
            return (
                Unit.objects.exclude_blocked()
                .with_effective_source()
                .filter(query)
                .prefetch()
                .prefetch_bulk()
            )

        id_hashes_by_group: dict[tuple[int, int], list[int]] = defaultdict(list)
        for match in matches:
            id_hashes_by_group[
                match["plural_id"], match["check_source_language"]
            ].append(match["id_hash"])
        for key, id_hashes in id_hashes_by_group.items():
            query |= Q(
                translation_id__in=translation_groups[key], id_hash__in=id_hashes
            )
        return Unit.objects.filter(query).prefetch().prefetch_bulk()


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
    version_added = "4.18"

    def should_skip(self, unit: Unit):
        if unit.translation.plural.number <= 1 or not any(unit.get_target_plurals()):
            return True
        return super().should_skip(unit)

    def check_target_unit(self, sources: list[str], targets: list[str], unit: Unit):
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Unit

        translation = unit.translation
        component = translation.component

        if not component.allow_translation_propagation:
            return False

        # Use last result if checks are batched
        if component.batch_checks:
            return self.handle_batch(unit, component)

        return Unit.objects.same_target(unit).exists()

    def get_description(self, check_obj: Check):
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Unit

        other_sources = (
            Unit.objects.same_target(check_obj.unit)
            .values_list(F("check_source"), flat=True)
            .distinct()
        )

        return format_html(
            "{} {}",
            ngettext(
                "Other source string:", "Other source strings:", len(other_sources)
            ),
            format_html_join_comma(
                "{}", ((gettext("“%s”") % source,) for source in other_sources)
            ),
        )

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Target strings are checked in check_target_unit."""
        return False

    def check_component(self, component: Component) -> Iterable[Unit]:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Unit

        custom_sources = bool(component.project.translation_parent_language_ids)
        units = Unit.objects.exclude_blocked(custom_sources=custom_sources).filter(
            translation__component__project=component.project,
            translation__component__allow_translation_propagation=True,
            state__gte=STATE_TRANSLATED,
        )
        # Lower has no effect here, but we want to utilize index
        source_units = units.with_effective_source(
            custom_sources=custom_sources
        ).exclude(target__lower__md5=MD5(Value("")))

        # List strings with different sources
        # Limit this to 20 strings, otherwise the resulting query is too slow
        # Use ordering to make the limit deterministic
        matches = (
            source_units.values(
                "target", "translation__plural_id", "check_source_language"
            )
            .annotate(source__count=Count("check_source", distinct=True))
            .filter(source__count__gt=1)
            .order_by("target__lower__md5")[:20]
        )

        if not matches:
            return

        result = (
            source_units.filter(
                reduce(
                    lambda x, y: (
                        x
                        | (
                            Q(target__lower__md5=MD5(Lower(Value(y["target"]))))
                            & Q(target=y["target"])
                            & Q(translation__plural_id=y["translation__plural_id"])
                            & Q(check_source_language=y["check_source_language"])
                        )
                    ),
                    matches,
                    Q(),
                )
            )
            .prefetch()
            .prefetch_bulk()
        )

        # Filter out case differing source for case insensitive languages
        found: dict[tuple[int, int, str], set[str]] = defaultdict(set)
        remaining: list[tuple[tuple[int, int, str], Unit]] = []
        for unit in result:
            if not unit.translation.language.is_case_sensitive():
                key = (
                    unit.translation.plural_id,
                    unit.effective_source_language.pk,
                    unit.target,
                )
                lower_source = unit.effective_source.lower()
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

    SOURCE_ACTIONS: ClassVar[set[ActionEvents]] = {
        ActionEvents.SOURCE_CHANGE,
        ActionEvents.MARKED_EDIT,
    }

    TRACK_ACTIONS: ClassVar[set[ActionEvents]] = ACTIONS_REVERTABLE | SOURCE_ACTIONS

    def get_description(self, check_obj):
        unit = check_obj.unit
        target = self.check_target_unit(
            unit.get_effective_source_plurals(), unit.get_target_plurals(), unit
        )
        if not target:
            return super().get_description(check_obj)
        return gettext('Previous translation was "%s".') % target

    def should_skip_change(self, change: Change, unit: Unit) -> bool:
        # Skip translation entries adding needs editing string
        return change.details.get("state", STATE_TRANSLATED) < STATE_TRANSLATED

    def should_break_changes(self, change: Change) -> bool:
        # Stop changes processing on source string change or on
        # intentional marking as needing edit
        return change.action in self.SOURCE_ACTIONS

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

        changes = unit.change_set.filter(action__in=self.TRACK_ACTIONS).order()

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

    def get_fixup(self, unit: Unit) -> Iterable[FixupType] | None:
        target = self.check_target_unit(
            unit.get_effective_source_plurals(), unit.get_target_plurals(), unit
        )
        if not target:
            return None
        return [("plurals", split_plural(target))]

    def check_component(self, component: Component) -> Iterable[Unit]:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Change, Unit

        units = (
            Unit.objects.filter(
                translation__component=component,
                change__action__in=self.TRACK_ACTIONS,
                state__lt=STATE_TRANSLATED,
            )
            .prefetch_related(
                Prefetch(
                    "change_set",
                    queryset=Change.objects.filter(
                        action__in=self.TRACK_ACTIONS
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
