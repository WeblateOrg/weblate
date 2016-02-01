# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


class TranslationChecklist(list):
    """Simple list wrapper for translation checklist"""

    def add_if(self, name, label, count, level, words=None):
        """Add to list if there are matches"""
        if count > 0:
            self.add(name, label, count, level, words)

    def add(self, name, label, count, level, words=None):
        """Adds item to the list"""
        if words is not None:
            self.append((name, label, count, level, words))
        else:
            self.append((name, label, count, level))
