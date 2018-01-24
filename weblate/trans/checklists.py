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


class TranslationChecklist(list):
    """Simple list wrapper for translation checklist"""

    def add_if(self, stats, name, label, level):
        """Add to list if there are matches"""
        if getattr(stats, name) > 0:
            self.add(stats, name, label, level)

    def add(self, stats, name, label, level):
        """Add item to the list"""
        self.append((
            name,
            label,
            getattr(stats, name),
            level,
            getattr(stats, '{}_words'.format(name))
        ))
