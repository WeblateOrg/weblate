# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import reduce

from django.db.models import Count, Prefetch, Q
from django.db.models.functions import MD5
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheck
from weblate.utils.state import STATE_TRANSLATED


class PluralsCheck(TargetCheck):
    """Check for incomplete plural forms."""

    check_id = "plurals"
    name = _("Missing plurals")
    description = _("Some plural forms are untranslated")

    def should_skip(self, unit):
        if unit.translation.component.is_multivalue:
            return True
        return super().should_skip(unit)

    def check_target_unit(self, sources, targets, unit):
        # Is this plural?
        if len(sources) == 1:
            return False
        # Is at least something translated?
        if targets == len(targets) * [""]:
            return False
        # Check for empty translation
        return "" in targets

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False


class SamePluralsCheck(TargetCheck):
    """Check for same plural forms."""

    check_id = "same-plurals"
    name = _("Same plurals")
    description = _("Some plural forms are translated in the same way")

    def check_target_unit(self, sources, targets, unit):
        # Is this plural?
        if len(sources) == 1 or len(targets) == 1:
            return False
        if not targets[0]:
            return False
        return len(set(targets)) == 1

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False


class ConsistencyCheck(TargetCheck):
    """Check for inconsistent translations."""

    check_id = "inconsistent"
    name = _("Inconsistent")
    description = _(
        "This string has more than one translation in this project "
        "or is untranslated in some components."
    )
    ignore_untranslated = False
    propagates = True
    batch_project_wide = True
    skip_suggestions = True

    def check_target_unit(self, sources, targets, unit):
        component = unit.translation.component
        if not component.allow_translation_propagation:
            return False

        # Use last result if checks are batched
        if component.batch_checks:
            return self.handle_batch(unit, component)

        for other in unit.same_source_units:
            if unit.target == other.target:
                continue
            if unit.translated or other.translated:
                return True
        return False

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False

    def check_component(self, component):
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


class ReusedCheck(TargetCheck):
    """Check for reused translations."""

    check_id = "reused"
    name = _("Reused translation")
    description = _("Different strings are translated same.")
    propagates = True
    batch_project_wide = True
    skip_suggestions = True

    def check_target_unit(self, sources, targets, unit):
        component = unit.translation.component
        if not component.allow_translation_propagation:
            return False

        # Use last result if checks are batched
        if component.batch_checks:
            return self.handle_batch(unit, component)

        for other in unit.same_target_units:
            if unit.context == other.context:
                continue
            return True
        return False

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False

    def check_component(self, component):
        from weblate.trans.models import Unit

        units = Unit.objects.filter(
            translation__component__project=component.project,
            translation__component__allow_translation_propagation=True,
            state__gte=STATE_TRANSLATED,
        )
        units = units.annotate(target__md5=MD5("target"))

        # List strings with different sources
        # Limit this to 100 strings, otherwise the resulting query is way too complex
        matches = (
            units.values("target__md5", "translation__language", "translation__plural")
            .annotate(id_hash__count=Count("id_hash", distinct=True))
            .filter(id_hash__count__gt=1)
            .order_by("target__md5")[:100]
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


class TranslatedCheck(TargetCheck):
    """Check for inconsistent translations."""

    check_id = "translated"
    name = _("Has been translated")
    description = _("This string has been translated in the past")
    ignore_untranslated = False
    skip_suggestions = True

    def get_description(self, check_obj):
        unit = check_obj.unit
        target = self.check_target_unit(unit.source, unit.target, unit)
        if not target:
            return super().get_description(check_obj)
        return _('Previous translation was "%s".') % target

    def should_skip_change(self, change, unit):
        from weblate.trans.models import Change

        # Skip automatic translation entries adding needs editing string
        return (
            change.action == Change.ACTION_AUTO
            and change.details.get("state", STATE_TRANSLATED) < STATE_TRANSLATED
        )

    @staticmethod
    def should_break_changes(change):
        from weblate.trans.models import Change

        # Stop changes processin on source string change or on
        # intentional marking as needing edit
        return change.action in (Change.ACTION_SOURCE_CHANGE, Change.ACTION_MARKED_EDIT)

    def check_target_unit(self, sources, targets, unit):
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

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False

    def get_fixup(self, unit):
        target = self.check_target_unit(unit.source, unit.target, unit)
        if not target:
            return None
        return [(".*", target, "u")]

    def check_component(self, component):
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
