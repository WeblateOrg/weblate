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

"""Tests for placeholder quality checks."""


from weblate.checks.placeholders import PlaceholderCheck, RegexCheck
from weblate.checks.tests.test_checks import CheckTestCase


class PlaceholdersTest(CheckTestCase):
    check = PlaceholderCheck()

    def setUp(self):
        super().setUp()
        self.test_good_matching = ("string $URL$", "string $URL$", "placeholders:$URL$")
        self.test_good_none = ("string", "string", "placeholders:")
        self.test_good_ignore = ("$URL", "$OTHER")
        self.test_failure_1 = ("string $URL$", "string", "placeholders:$URL$")
        self.test_failure_2 = ("string $URL$", "string $URL", "placeholders:$URL$")
        self.test_failure_3 = (
            "string $URL$ $2$",
            "string $URL$",
            "placeholders:$URL$:$2$:",
        )
        self.test_highlight = ("placeholders:$URL$", "See $URL$", [(4, 9, "$URL$")])

    def do_test(self, expected, data, lang=None):
        return


class RegexTest(CheckTestCase):
    check = RegexCheck()

    def setUp(self):
        super().setUp()
        self.test_good_matching = ("string URL", "string URL", "regex:URL")
        self.test_good_none = ("string", "string", "regex:")
        self.test_failure_1 = ("string URL", "string", "regex:URL")
        self.test_failure_2 = ("string URL", "string url", "regex:URL")
        self.test_failure_3 = ("string URL", "string URL", "regex:^URL$")
        self.test_highlight = ("regex:URL", "See URL", [(4, 7, "URL")])

    def do_test(self, expected, data, lang=None):
        return
