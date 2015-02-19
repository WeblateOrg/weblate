# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
"""
Weblate wrapper around translate-toolkit formats to add missing
functionality.
"""
import json
from translate.storage.jsonl10n import JsonFile as JsonFileTT


class JsonFile(JsonFileTT):
    """
    Workaround ttkit bug on not including added units in saved file.
    """
    def __str__(self):
        data = {}
        # This is really broken for many reasons, but works for
        # simple JSON files.
        for unit in self.units:
            data[unit.getid().lstrip('.')] = unit.source
        return json.dumps(
            data, sort_keys=True, indent=4, ensure_ascii=False
        ).encode('utf-8')
