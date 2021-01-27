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

from functools import reduce

from django.db.models import Count, Prefetch, Q
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheck
from weblate.utils.state import STATE_TRANSLATED


class PluralsCheck(TargetCheck):
    """Check for incomplete plural forms."""

    check_id = "plurals"
    name = _("Missing plurals")
    description = _("Some plural forms are not translated")

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
        if targets[0] == "":
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
        "or is not translated in some components."
    )
    ignore_untranslated = False
    propagates = True

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
        matches = (
            units.values("source", "context", "translation__language")
            .annotate(Count("target", distinct=True))
            .filter(target__count__gt=1)
        )

        if not matches:
            return []

        return (
            units.filter(
                reduce(
                    lambda x, y: x
                    | (
                        Q(source=y["source"])
                        & Q(context=y["context"])
                        & Q(translation__language=y["translation__language"])
                    ),
                    matches,
                    Q(),
                )
            )
            .prefetch()
            .prefetch_full()
        )


class TranslatedCheck(TargetCheck):
    """Check for inconsistent translations."""

    check_id = "translated"
    name = _("Has been translated")
    description = _("This string has been translated in the past")
    ignore_untranslated = False

    def get_description(self, check_obj):
        unit = check_obj.unit
        target = self.check_target_unit(unit.source, unit.target, unit)
        if not target:
            return super().get_description(check_obj)
        return _('Previous translation was "%s".') % target

    @property
    def change_states(self):
        from weblate.trans.models import Change

        states = {Change.ACTION_SOURCE_CHANGE}
        states.update(Change.ACTIONS_CONTENT)
        return states

    def check_target_unit(self, sources, targets, unit):
        if unit.translated:
            return False

        component = unit.translation.component

        if component.batch_checks:
            return self.handle_batch(unit, component)

        from weblate.trans.models import Change

        changes = unit.change_set.filter(action__in=self.change_states).order()

        for action, target in changes.values_list("action", "target"):
            if action in Change.ACTIONS_CONTENT and target:
                return target
            if action == Change.ACTION_SOURCE_CHANGE:
                break

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
                change__action__in=self.change_states,
                state__lt=STATE_TRANSLATED,
            )
            .prefetch_related(
                Prefetch(
                    "change_set",
                    queryset=Change.objects.filter(
                        action__in=self.change_states
                    ).order(),
                    to_attr="recent_consistency_changes",
                )
            )
            .prefetch()
            .prefetch_full()
        )

        for unit in units:
            for change in unit.recent_consistency_changes:
                if change.action in Change.ACTIONS_CONTENT and change.target:
                    yield unit
                if change.action == Change.ACTION_SOURCE_CHANGE:
                    break
