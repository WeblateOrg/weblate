# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import reduce

from django.db.models import Count, Prefetch, Q, Value
from django.db.models.functions import MD5
from django.utils.translation import gettext, gettext_lazy, ngettext

from weblate.checks.base import TargetCheck
from weblate.utils.state import STATE_TRANSLATED


class PluralsCheck(TargetCheck):
    """Check for incomplete plural forms."""

    check_id = "plurals"
    name = gettext_lazy("Missing plurals")
    description = gettext_lazy("Some plural forms are untranslated")

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
    name = gettext_lazy("Same plurals")
    description = gettext_lazy("Some plural forms are translated in the same way")

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
    name = gettext_lazy("Inconsistent")
    description = gettext_lazy(
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

    def should_skip(self, unit):
        if unit.translation.plural.number <= 1:
            return True
        return super().should_skip(unit)

    def get_same_target_units(self, unit):
        from weblate.trans.models import Unit

        translation = unit.translation
        component = translation.component
        return Unit.objects.filter(
            target__md5=MD5(Value(unit.target)),
            translation__component__project_id=component.project_id,
            translation__language_id=translation.language_id,
            translation__component__source_language_id=component.source_language_id,
            translation__component__allow_translation_propagation=True,
            translation__plural_id=translation.plural_id,
            translation__plural__number__gt=1,
        ).exclude(source__md5=MD5(Value(unit.source)))

    def check_target_unit(self, sources, targets, unit):
        translation = unit.translation
        component = translation.component
        if not component.allow_translation_propagation:
            return False

        # Use last result if checks are batched
        if component.batch_checks:
            return self.handle_batch(unit, component)

        return self.get_same_target_units(unit).exists()

    def get_description(self, check_obj):
        other_sources = (
            self.get_same_target_units(check_obj.unit)
            .values_list("source", flat=True)
            .distinct()
        )

        return ngettext(
            "Other source string: %s", "Other source strings: %s", len(other_sources)
        ) % ", ".join(gettext("“%s”") % source for source in other_sources)

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

        # List strings with different sources
        # Limit this to 100 strings, otherwise the resulting query is way too complex
        matches = (
            units.values("target__md5", "translation__language", "translation__plural")
            .annotate(source__count=Count("source", distinct=True))
            .filter(source__count__gt=1)
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
