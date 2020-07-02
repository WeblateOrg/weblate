#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
        for other in unit.same_source_units:
            if unit.target == other.target:
                continue
            if unit.translated or other.state >= STATE_TRANSLATED:
                return True
        return False

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False


class TranslatedCheck(TargetCheck):
    """Check for inconsistent translations."""

    check_id = "translated"
    name = _("Has been translated")
    description = _("This string has been translated in the past")
    ignore_untranslated = False

    def get_description(self, check=None):
        unit = check.unit
        target = self.check_target_unit(unit.source, unit.target, unit)
        self.description = (
            _(
                'This string has been translated in the past. \
                Last Translation was "%s"'
            )
            % target
        )
        return self.description

    def check_target_unit(self, sources, targets, unit):
        if unit.translated:
            return False

        from weblate.trans.models import Change

        states = {Change.ACTION_SOURCE_CHANGE}
        states.update(Change.ACTIONS_CONTENT)

        changes = unit.change_set.filter(action__in=states).order()

        for action, target in changes.values_list("action", "target"):
            if action in Change.ACTIONS_CONTENT:
                return target
            if action == Change.ACTION_SOURCE_CHANGE:
                break

        return False

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False
