#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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


class AutoFix:
    """Base class for AutoFixes."""

    fix_id = "auto"

    def get_identifier(self):
        return self.fix_id

    def fix_single_target(self, target, source, unit):
        """Fix a single target, implement this method in subclasses."""
        raise NotImplementedError()

    def fix_target(self, target, unit):
        """Return a target translation array with a single fix applied."""
        source_strings = unit.get_source_plurals()
        if len(source_strings) == 1 and len(target) == 1:
            results = [self.fix_single_target(target[0], source_strings[0], unit)]
        else:
            source_plural = unit.translation.component.source_language.plural
            target_plural = unit.translation.plural
            source_examples = {tuple(l): i for i, l in source_plural.examples.items()}
            plurals_map = [
                source_examples.get(
                    tuple(target_plural.examples.get(target_index, [])), -1
                )
                for target_index in range(target_plural.number)
            ]
            results = [
                self.fix_single_target(text, source_strings[plurals_map[i]], unit)
                for i, text in enumerate(target)
            ]
        return [r[0] for r in results], max(r[1] for r in results)
