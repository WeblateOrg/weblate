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

"""Tests for placeholder quality checks."""


from weblate.checks.flags import Flags
from weblate.checks.models import Check
from weblate.checks.placeholders import PlaceholderCheck, RegexCheck
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit
from weblate.trans.models import Unit


class PlaceholdersTest(CheckTestCase):
    check = PlaceholderCheck()

    def setUp(self):
        super().setUp()
        self.test_good_matching = ("string $URL$", "string $URL$", "placeholders:$URL$")
        self.test_good_none = ("string", "string", "placeholders:")
        self.test_good_ignore = ("$URL", "$OTHER", "")
        self.test_failure_1 = ("string $URL$", "string", "placeholders:$URL$")
        self.test_failure_2 = ("string $URL$", "string $URL", "placeholders:$URL$")
        self.test_failure_3 = (
            "string $URL$ $2$",
            "string $URL$",
            "placeholders:$URL$:$2$:",
        )
        self.test_highlight = ("placeholders:$URL$", "See $URL$", [(4, 9, "$URL$")])

    def do_test(self, expected, data, lang=None):
        # Skip using check_single as the Check does not use that
        return

    def test_description(self):
        unit = Unit(source="string $URL$", target="string")
        unit.__dict__["all_flags"] = Flags("placeholders:$URL$")
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "Following format strings are missing: $URL$",
        )

    def test_regexp(self):
        unit = Unit(source="string $URL$", target="string $FOO$")
        unit.__dict__["all_flags"] = Flags(r"""placeholders:r"\$[^$]*\$" """)
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "Following format strings are missing: $URL$"
            "<br />Following format strings are extra: $FOO$",
        )


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
        # Skip using check_single as the Check does not use that
        return

    def test_description(self):
        unit = Unit(source="string URL", target="string")
        unit.__dict__["all_flags"] = Flags("regex:URL")
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "Translation does not match regular expression: <code>URL</code>",
        )

    def test_check_highlight_groups(self):
        unit = MockUnit(
            None,
            r'regex:"((?:@:\(|\{)[^\)\}]+(?:\)|\}))"',
            self.default_lang,
            "@:(foo.bar.baz) | @:(hello.world) | {foo32}",
        )
        self.assertEqual(
            self.check.check_highlight(unit.source, unit),
            [
                (0, 15, "@:(foo.bar.baz)"),
                (18, 33, "@:(hello.world)"),
                (36, 43, "{foo32}"),
            ],
        )
