# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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


class AutoFix(object):
    """Base class for AutoFixes"""
    fix_id = 'auto'

    def get_identifier(self):
        return self.fix_id

    def fix_single_target(self, target, source, unit):
        """Fix a single target, implement this method in subclasses."""
        raise NotImplementedError()

    def fix_target(self, target, unit):
        """Return a target translation array with a single fix applied."""
        source = unit.get_source_plurals()[0]
        results = [self.fix_single_target(t, source, unit) for t in target]
        return [r[0] for r in results], max([r[1] for r in results])
