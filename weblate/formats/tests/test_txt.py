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
"""File format specific behavior."""

import os.path

from weblate.formats.tests.test_formats import AutoFormatTest
from weblate.formats.txt import AppStoreFormat
from weblate.trans.tests.utils import get_test_file

APPSTORE_FILE = get_test_file("short_description.txt")


class AppStoreFormatTest(AutoFormatTest):
    FORMAT = AppStoreFormat
    FILE = APPSTORE_FILE
    MIME = "text/plain"
    EXT = "txt"
    COUNT = 1
    MASK = "market/*"
    EXPECTED_PATH = "market/cs_CZ"
    FIND = "Hello world"
    FIND_CONTEXT = "short_description.txt:1"
    FIND_MATCH = "Hello world"
    MATCH = None
    BASE = APPSTORE_FILE
    EXPECTED_FLAGS = "max-length:80"

    def parse_file(self, filename):
        return self.FORMAT(os.path.dirname(filename))
