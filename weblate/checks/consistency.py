# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from functools import reduce
from itertools import batched
from typing import TYPE_CHECKING, ClassVar, Literal

from django.db.models import (
    BooleanField,
    Case,
    Exists,
    F,
    OuterRef,
    Prefetch,
    Q,
    Value,
    When,
)
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
    from weblate.trans.models import Change, Component, Project, Unit
    from weblate.trans.models.unit import UnitQuerySet

    from .base import FixupType


def _visible_peer_query(project: Project, *, custom_sources: bool) -> UnitQuerySet:
    """Build a peer query relative to an outer unit in the same project."""
    from weblate.trans.models import Unit  # ruff: ignore[import-outside-top-level]

    return (
        Unit.objects.exclude_blocked(custom_sources=custom_sources)
        .with_effective_source(custom_sources=custom_sources, select=False)
        .filter(
            translation__component__project=project,
            translation__component__allow_translation_propagation=True,
            translation__plural_id=OuterRef("translation__plural_id"),
            check_source_language=OuterRef("check_source_language"),
        )
        .filter(
            Q(translation__component__restricted=False)
            | Q(translation__component_id=OuterRef("translation__component_id"))
        )
    )


def inconsistent_peer_exists(
    project: Project, *, custom_sources: bool, translated_only: bool = False
) -> Exists:
    """Whether an outer unit has an accessible peer with a different target."""
    peers = (
        _visible_peer_query(project, custom_sources=custom_sources)
        .filter(
            translation__language_id=OuterRef("translation__language_id"),
            context=OuterRef("context"),
        )
        .filter(Q(check_source=OuterRef("check_source")))
    )
    if custom_sources:
        for field in ("number", "formula", "type"):
            peers = peers.filter(
                **{f"check_source_{field}": OuterRef(f"check_source_{field}")}
            )
    else:
        peers = peers.filter(id_hash=OuterRef("id_hash"))
    if translated_only:
        peers = peers.filter(state__gte=STATE_TRANSLATED)
    return Exists(peers.exclude(target=OuterRef("target")))


def reused_peer_exists(
    project: Project, *, custom_sources: bool, folded: bool = False
) -> Exists:
    """Whether an outer unit has an accessible peer with a different source."""
    peers = _visible_peer_query(project, custom_sources=custom_sources).filter(
        state__gte=STATE_TRANSLATED,
        target=OuterRef("target"),
        target__lower__md5=MD5(Lower(OuterRef("target"))),
        translation__plural__number__gt=1,
    )
    if custom_sources:
        for field in ("number", "formula", "type"):
            peers = peers.filter(
                **{f"check_source_{field}": OuterRef(f"check_source_{field}")}
            )
    if folded:
        peers = peers.exclude(
            Q(check_source__lower__md5=MD5(Lower(OuterRef("check_source"))))
        )
    else:
        peers = peers.exclude(Q(check_source=OuterRef("check_source")))
    return Exists(peers)


def reused_peer_condition(project: Project, *, custom_sources: bool) -> Case:
    """Apply target-language case sensitivity to the reused peer lookup."""
    from weblate.lang.models import Language  # ruff: ignore[import-outside-top-level]

    insensitive = [
        language.pk
        for language in Language.objects.all()
        if not language.is_case_sensitive()
    ]
    return Case(
        When(
            translation__language_id__in=insensitive,
            then=reused_peer_exists(
                project, custom_sources=custom_sources, folded=True
            ),
        ),
        default=reused_peer_exists(project, custom_sources=custom_sources),
        output_field=BooleanField(),
    )


def stale_project_check_units(project: Project, check_id: str) -> UnitQuerySet:
    """Find stored-check units without a peer visible after a boundary change."""
    from weblate.trans.models import Unit  # ruff: ignore[import-outside-top-level]

    custom_sources = bool(project.translation_parent_language_ids)
    units = Unit.objects.with_effective_source(
        custom_sources=custom_sources, select=False
    ).filter(translation__component__project=project)
    if check_id == "inconsistent":
        condition = Case(
            When(
                state__gte=STATE_TRANSLATED,
                then=inconsistent_peer_exists(project, custom_sources=custom_sources),
            ),
            default=inconsistent_peer_exists(
                project, custom_sources=custom_sources, translated_only=True
            ),
            output_field=BooleanField(),
        )
    else:
        condition = reused_peer_condition(project, custom_sources=custom_sources)
    return units.annotate(has_visible_peer=condition).filter(
        Q(has_visible_peer=False)
        | Q(translation__component__allow_translation_propagation=False)
    )


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

    def evaluate_propagated(self, units: UnitQuerySet) -> Iterable[tuple[Unit, bool]]:
        public_targets = set()
        public_translated_targets = set()
        restricted_targets: dict[int, set[str]] = defaultdict(set)
        restricted_translated_targets: dict[int, set[str]] = defaultdict(set)
        for target, state, component_id, restricted in units.values_list(
            "target",
            "state",
            "translation__component_id",
            "translation__component__restricted",
        ):
            if restricted:
                restricted_targets[component_id].add(target)
                if state >= STATE_TRANSLATED:
                    restricted_translated_targets[component_id].add(target)
            else:
                public_targets.add(target)
                if state >= STATE_TRANSLATED:
                    public_translated_targets.add(target)
        for unit in units.iterator(chunk_size=500):
            component = unit.translation.component
            if unit.translated:
                others = (
                    public_targets | restricted_targets[component.pk]
                    if component.restricted
                    else public_targets
                )
            else:
                others = (
                    public_translated_targets
                    | restricted_translated_targets[component.pk]
                    if component.restricted
                    else public_translated_targets
                )
            yield (
                unit,
                (
                    self.applies_to_propagated_unit(unit)
                    and not self.ignore_state(unit)
                    and not self.should_skip(unit)
                    and (len(others) > 1 or bool(others and unit.target not in others))
                ),
            )

    def check_target_unit(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> bool:
        component = unit.translation.component
        if not component.allow_translation_propagation:
            return False

        # Use last result if checks are batched
        if component.batch_checks:
            return self.handle_batch(unit, component)

        others = unit.propagated_units.filter_restricted_peers(unit).exclude(
            target=unit.target
        )
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
            (
                "check_source",
                "context",
                "check_source_language",
                "check_source_number",
                "check_source_formula",
                "check_source_type",
            )
            if custom_sources
            else ("id_hash", "check_source_language")
        )
        ordering = (
            (*fields, "plural_id")
            if custom_sources
            else ("id_hash", "plural_id", "check_source_language")
        )
        # Select only groups with an accessible conflicting peer before limiting.
        # This keeps rejected restricted-only groups out of the bounded result.
        matches = (
            Unit.objects.exclude_blocked(custom_sources=custom_sources)
            .filter(
                translation__component__project=component.project,
                translation__component__allow_translation_propagation=True,
            )
            .with_effective_source(custom_sources=custom_sources)
            .annotate(
                has_peer=Case(
                    When(
                        state__gte=STATE_TRANSLATED,
                        then=inconsistent_peer_exists(
                            component.project, custom_sources=custom_sources
                        ),
                    ),
                    default=inconsistent_peer_exists(
                        component.project,
                        custom_sources=custom_sources,
                        translated_only=True,
                    ),
                    output_field=BooleanField(),
                )
            )
            .filter(has_peer=True)
            .values(*fields)
            .annotate(plural_id=F("translation__plural_id"))
            .order_by(*ordering)
            .distinct()[:100]
        )

        found: list[Unit] = []
        valid_groups = 0
        for match_batch in batched(matches.iterator(chunk_size=100), 100):
            query = Q()
            if custom_sources:
                for match in match_batch:
                    query |= Q(
                        translation_id__in=translation_groups[match["plural_id"], None],
                        **{field: match[field] for field in fields},
                    )
                result = (
                    Unit.objects.exclude_blocked()
                    .with_effective_source()
                    .filter(query)
                    .prefetch()
                    .prefetch_bulk()
                )
            else:
                id_hashes_by_group: dict[tuple[int, int], list[int]] = defaultdict(list)
                for match in match_batch:
                    id_hashes_by_group[
                        match["plural_id"], match["check_source_language"]
                    ].append(match["id_hash"])
                for group_key, id_hashes in id_hashes_by_group.items():
                    query |= Q(
                        translation_id__in=translation_groups[group_key],
                        id_hash__in=id_hashes,
                    )
                result = Unit.objects.filter(query).prefetch().prefetch_bulk()

            public_targets: dict[tuple, set[str]] = defaultdict(set)
            restricted_targets: dict[tuple, set[str]] = defaultdict(set)
            candidates: dict[tuple, list[Unit]] = defaultdict(list)
            for unit in result:
                source_key: tuple
                if custom_sources:
                    source_key = (
                        unit.translation.plural_id,
                        unit.check_source,
                        unit.context,
                        unit.check_source_language,
                        unit.check_source_number,
                        unit.check_source_formula,
                        unit.check_source_type,
                    )
                else:
                    source_key = (
                        unit.translation.plural_id,
                        unit.translation.component.source_language_id,
                        unit.id_hash,
                    )
                peer = unit.translation.component
                if peer.restricted:
                    restricted_targets[source_key, peer.pk].add(unit.target)
                else:
                    public_targets[source_key].add(unit.target)
                candidates[source_key].append(unit)

            for match in match_batch:
                source_key = (
                    (match["plural_id"], *(match[field] for field in fields))
                    if custom_sources
                    else (
                        match["plural_id"],
                        match["check_source_language"],
                        match["id_hash"],
                    )
                )
                eligible = [
                    unit
                    for unit in candidates[source_key]
                    if len(
                        public_targets[source_key]
                        | restricted_targets[source_key, unit.translation.component_id]
                        if unit.translation.component.restricted
                        else public_targets[source_key]
                    )
                    > 1
                ]
                if eligible:
                    found.extend(eligible)
                    valid_groups += 1
                    if valid_groups == 100:
                        return found
        return found


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

    def evaluate_propagated(self, units: UnitQuerySet) -> Iterable[tuple[Unit, bool]]:
        source_field = (
            "check_source" if "check_source" in units.query.annotations else "source"
        )
        units = units.annotate(
            propagated_source=F(source_field),
            propagated_source_folded=Lower(source_field),
        )
        public_sources = set()
        public_folded_sources = set()
        restricted_sources: dict[int, set[str]] = defaultdict(set)
        restricted_folded_sources: dict[int, set[str]] = defaultdict(set)
        for source, folded, component_id, restricted in units.filter(
            state__gte=STATE_TRANSLATED
        ).values_list(
            "propagated_source",
            "propagated_source_folded",
            "translation__component_id",
            "translation__component__restricted",
        ):
            if restricted:
                restricted_sources[component_id].add(source)
                restricted_folded_sources[component_id].add(folded)
            else:
                public_sources.add(source)
                public_folded_sources.add(folded)
        for unit in units.iterator(chunk_size=500):
            component = unit.translation.component
            if unit.translation.language.is_case_sensitive():
                distinct_sources = (
                    public_sources | restricted_sources[component.pk]
                    if component.restricted
                    else public_sources
                )
                source = unit.propagated_source
            else:
                distinct_sources = (
                    public_folded_sources | restricted_folded_sources[component.pk]
                    if component.restricted
                    else public_folded_sources
                )
                source = unit.propagated_source_folded
            yield (
                unit,
                (
                    self.applies_to_propagated_unit(unit)
                    and not self.ignore_state(unit)
                    and not self.should_skip(unit)
                    and (
                        len(distinct_sources) > 1
                        or bool(distinct_sources and source not in distinct_sources)
                    )
                ),
            )

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
        plural_fields = (
            ("check_source_number", "check_source_formula", "check_source_type")
            if custom_sources
            else ()
        )
        matches = (
            source_units.annotate(
                has_peer=reused_peer_condition(
                    component.project, custom_sources=custom_sources
                )
            )
            .filter(has_peer=True)
            .values(
                "target",
                "translation__plural_id",
                "check_source_language",
                *plural_fields,
            )
            .annotate(target_hash=MD5(Lower("target")))
            .order_by(
                "target_hash",
                "target",
                "translation__plural_id",
                "check_source_language",
                *plural_fields,
            )
            .distinct()[:20]
        )
        valid_groups = 0
        for match_batch in batched(matches.iterator(chunk_size=20), 20):
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
                                & Q(**{field: y[field] for field in plural_fields})
                            )
                        ),
                        match_batch,
                        Q(),
                    )
                )
                .prefetch()
                .prefetch_bulk()
            )

            # Keep the same visibility boundary as same_target().
            public: dict[tuple, set[str]] = defaultdict(set)
            restricted: dict[tuple, set[str]] = defaultdict(set)
            public_folded: dict[tuple, set[str]] = defaultdict(set)
            restricted_folded: dict[tuple, set[str]] = defaultdict(set)
            candidates: dict[tuple, list[Unit]] = defaultdict(list)
            for unit in result:
                peer = unit.translation.component
                key = (
                    unit.translation.plural_id,
                    unit.effective_source_language.pk,
                    unit.target,
                    *(getattr(unit, field) for field in plural_fields),
                )
                source = unit.effective_source
                if peer.restricted:
                    restricted[key, peer.pk].add(source)
                    restricted_folded[key, peer.pk].add(source.lower())
                else:
                    public[key].add(source)
                    public_folded[key].add(source.lower())
                candidates[key].append(unit)

            for match in match_batch:
                key = (
                    match["translation__plural_id"],
                    match["check_source_language"],
                    match["target"],
                    *(match[field] for field in plural_fields),
                )
                eligible = []
                for unit in candidates[key]:
                    peer = unit.translation.component
                    if unit.translation.language.is_case_sensitive():
                        sources = (
                            public[key] | restricted[key, peer.pk]
                            if peer.restricted
                            else public[key]
                        )
                    else:
                        sources = (
                            public_folded[key] | restricted_folded[key, peer.pk]
                            if peer.restricted
                            else public_folded[key]
                        )
                    if len(sources) > 1:
                        eligible.append(unit)
                if eligible:
                    yield from eligible
                    valid_groups += 1
                    if valid_groups == 20:
                        return


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
