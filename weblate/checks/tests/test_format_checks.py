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

"""Tests for quality checks."""


from django.test import SimpleTestCase

from weblate.checks.format import (
    CFormatCheck,
    CSharpFormatCheck,
    ESTemplateLiteralsCheck,
    I18NextInterpolationCheck,
    JavaFormatCheck,
    JavaMessageFormatCheck,
    LuaFormatCheck,
    MultipleUnnamedFormatsCheck,
    PercentPlaceholdersCheck,
    PerlFormatCheck,
    PHPFormatCheck,
    PythonBraceFormatCheck,
    PythonFormatCheck,
    SchemeFormatCheck,
    VueFormattingCheck,
)
from weblate.checks.models import Check
from weblate.checks.qt import QtFormatCheck, QtPluralCheck
from weblate.checks.ruby import RubyFormatCheck
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit
from weblate.lang.models import Language
from weblate.trans.models import Component, Translation, Unit
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.util import join_plural


class PythonFormatCheckTest(CheckTestCase):
    check = PythonFormatCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "python-format",
            "%sstring%d",
            [(0, 2, "%s"), (8, 10, "%d")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self):
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_space_format(self):
        self.assertTrue(
            self.check.check_format("%d % string", "%d % other", False, None)
        )

    def test_percent_format(self):
        self.assertFalse(
            self.check.check_format("%d%% string", "%d%% string", False, None)
        )
        self.assertTrue(
            self.check.check_format("12%% string", "12% string", False, None)
        )
        self.assertTrue(self.check.check_format("Save 12%%.", "Save 12%.", False, None))
        self.assertFalse(
            self.check.check_format("Save 12%%.", "Save 12 percent.", False, None)
        )

    def test_named_format(self):
        self.assertFalse(
            self.check.check_format("%(name)s string", "%(name)s string", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("%s string", "string", False, None))

    def test_missing_named_format(self):
        self.assertTrue(
            self.check.check_format("%(name)s string", "string", False, None)
        )

    def test_missing_named_format_ignore(self):
        self.assertFalse(
            self.check.check_format("%(name)s string", "string", True, None)
        )

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format("%s string", "%c string", False, None))

    def test_reordered_format(self):
        self.assertTrue(
            self.check.check_format("%s %d string", "%d %s string", False, None)
        )

    def test_wrong_named_format(self):
        self.assertTrue(
            self.check.check_format("%(name)s string", "%(jmeno)s string", False, None)
        )

    def test_reordered_named_format(self):
        self.assertFalse(
            self.check.check_format(
                "%(name)s %(foo)s string", "%(foo)s %(name)s string", False, None
            )
        )

    def test_reordered_named_format_long(self):
        self.assertFalse(
            self.check.check_format(
                "%(count)d strings into %(languages)d languages %(percent)d%%",
                "%(languages)d dil içinde %(count)d satır %%%(percent)d",
                False,
                None,
            )
        )

    def test_feedback(self):
        self.assertEqual(
            self.check.check_format("%(count)d", "%(languages)d", False, None),
            {"missing": ["(count)d"], "extra": ["(languages)d"]},
        )
        self.assertEqual(
            self.check.check_format("%(count)d", "count", False, None),
            {"missing": ["(count)d"], "extra": []},
        )
        self.assertEqual(
            self.check.check_format(
                "%(count)d", "%(count)d %(languages)d", False, None
            ),
            {"missing": [], "extra": ["(languages)d"]},
        )
        self.assertEqual(
            self.check.check_format("%d", "%s", False, None),
            {"missing": ["d"], "extra": ["s"]},
        )
        self.assertEqual(
            self.check.check_format("%d", "ds", False, None),
            {"missing": ["d"], "extra": []},
        )
        self.assertEqual(
            self.check.check_format("%d", "%d %s", False, None),
            {"missing": [], "extra": ["s"]},
        )
        self.assertEqual(
            self.check.check_format("%d %d", "%d", False, None),
            {"missing": ["d"], "extra": []},
        )

    def test_description(self):
        unit = Unit(
            source="%(count)d",
            target="%(languages)d",
            extra_flags="python-format",
        )
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "Following format strings are missing: %(count)d<br />"
            "Following format strings are extra: %(languages)d",
        )

    def test_description_nolocation(self):
        unit = Unit(
            source="%d %s",
            target="%s %d",
            extra_flags="python-format",
        )
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "Following format strings are wrongly ordered: %d, %s",
        )


class PHPFormatCheckTest(CheckTestCase):
    check = PHPFormatCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "php-format",
            "%sstring%d",
            [(0, 2, "%s"), (8, 10, "%d")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self):
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_named_format(self):
        self.assertFalse(
            self.check.check_format("%1$s string", "%1$s string", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("%s string", "string", False, None))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format("%1$s string", "string", False, None))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format("%1$s string", "string", True, None))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format("%s string", "%c string", False, None))

    def test_double_format(self):
        self.assertTrue(
            self.check.check_format("%s string", "%s%s string", False, None)
        )

    def test_reorder_format(self):
        self.assertFalse(
            self.check.check_format("%1$s %2$s string", "%2$s %1$s string", False, None)
        )

    def test_wrong_named_format(self):
        self.assertTrue(
            self.check.check_format("%1$s string", "%s string", False, None)
        )

    def test_wrong_percent_format(self):
        self.assertTrue(
            self.check.check_format("%s%% (0.1%%)", "%s%% (0.1%x)", False, None)
        )

    def test_missing_percent_format(self):
        self.assertFalse(
            self.check.check_format("%s%% %%", "%s%% percent", False, None)
        )

    def test_space_format(self):
        self.assertTrue(
            self.check.check_format("%d % string", "%d % other", False, None)
        )


class SchemeFormatCheckTest(CheckTestCase):
    check = SchemeFormatCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "scheme-format",
            "~sstring~d",
            [(0, 2, "~s"), (8, 10, "~d")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self):
        self.assertFalse(self.check.check_format("~s string", "~s string", False, None))

    def test_named_format(self):
        self.assertFalse(
            self.check.check_format("~0@*~s string", "~0@*~s string", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("~s string", "string", False, None))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format("~1@*~s string", "string", False, None))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format("~1@*~s string", "string", True, None))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format("~s string", "~c string", False, None))

    def test_double_format(self):
        self.assertTrue(
            self.check.check_format("~s string", "~s~s string", False, None)
        )

    def test_reorder_format(self):
        self.assertFalse(
            self.check.check_format(
                "~1@*~s ~2@*~s string", "~2@*~s ~1@*~s string", False, None
            )
        )

    def test_wrong_named_format(self):
        self.assertTrue(
            self.check.check_format("~1@*~s string", "~s string", False, None)
        )

    def test_wrong_tilde_format(self):
        self.assertTrue(
            self.check.check_format("~s~~ (0.1~~)", "~s~~ (0.1~x)", False, None)
        )

    def test_missing_tilde_format(self):
        self.assertFalse(self.check.check_format("~s~~ ~~", "~s~~ tilde", False, None))


class CFormatCheckTest(CheckTestCase):
    check = CFormatCheck()
    flag = "c-format"

    def setUp(self):
        super().setUp()
        self.test_highlight = (self.flag, "%sstring%d", [(0, 2, "%s"), (8, 10, "%d")])

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self):
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_named_format(self):
        self.assertFalse(
            self.check.check_format("%10s string", "%10s string", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("%s string", "string", False, None))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format("%10s string", "string", False, None))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format("%10s string", "string", True, None))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format("%s string", "%c string", False, None))

    def test_wrong_named_format(self):
        self.assertTrue(
            self.check.check_format("%10s string", "%20s string", False, None)
        )

    def test_reorder_format(self):
        self.assertFalse(
            self.check.check_format("%1$s %2$s string", "%2$s %1$s string", False, None)
        )

    def test_locale_delimiter(self):
        self.assertFalse(
            self.check.check_format("lines: %6.3f", "radky: %'6.3f", False, None)
        )

    def test_ld_format(self):
        self.assertFalse(
            self.check.check_format(
                "%ld bytes (free %ld bytes, used %ld bytes)",
                "%l octets (%l octets libres, %l octets utilisés)",
                True,
                None,
            )
        )

    def test_parenthesis(self):
        self.assertFalse(self.check.check_format("(%.0lf%%)", "(%%%.0lf)", False, None))


class LuaFormatCheckTest(CFormatCheckTest):
    check = LuaFormatCheck()
    flag = "lua-format"


class PerlFormatCheckTest(CFormatCheckTest):
    check = PerlFormatCheck()
    flag = "perl-format"


class PythonBraceFormatCheckTest(CheckTestCase):
    check = PythonBraceFormatCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "python-brace-format",
            "{0}string{1}",
            [(0, 3, "{0}"), (9, 12, "{1}")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_position_format(self):
        self.assertFalse(
            self.check.check_format("{} string {}", "{} string {}", False, None)
        )

    def test_wrong_position_format(self):
        self.assertTrue(
            self.check.check_format("{} string", "{} string {}", False, None)
        )

    def test_named_format(self):
        self.assertFalse(
            self.check.check_format("{s1} string {s2}", "{s1} string {s2}", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("{} string", "string", False, None))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format("{s1} string", "string", False, None))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format("{s} string", "string", True, None))

    def test_wrong_format(self):
        self.assertTrue(
            self.check.check_format("{s} string", "{c} string", False, None)
        )

    def test_escaping(self):
        self.assertFalse(self.check.check_format("{{ string }}", "string", False, None))

    def test_attribute_format(self):
        self.assertFalse(
            self.check.check_format("{s.foo} string", "{s.foo} string", False, None)
        )

    def test_wrong_attribute_format(self):
        self.assertTrue(
            self.check.check_format("{s.foo} string", "{s.bar} string", False, None)
        )


class CSharpFormatCheckTest(CheckTestCase):
    check = CSharpFormatCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "c-sharp-format",
            "{0}string{1}",
            [(0, 3, "{0}"), (9, 12, "{1}")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_escaping_no_position(self):
        self.assertFalse(self.check.check_format("{{ string }}", "string", False, None))

    def test_simple_format(self):
        self.assertFalse(
            self.check.check_format("{0} strins", "{0} string", False, None)
        )

    def test_format_with_width(self):
        self.assertFalse(
            self.check.check_format("{0,1} strins", "{0,1} string", False, None)
        )

    def test_format_with_flag(self):
        self.assertFalse(
            self.check.check_format("{0:C2} strins", "{0:C2} string", False, None)
        )

    def test_full_format(self):
        self.assertFalse(
            self.check.check_format("{0,1:N0} strins", "{0,1:N0} string", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("{0} strins", "string", False, None))

    def test_missing_width_format(self):
        self.assertTrue(self.check.check_format("{0,1} strins", "string", False, None))

    def test_missing_flag_format(self):
        self.assertTrue(self.check.check_format("{0:C1} strins", "string", False, None))

    def test_missing_full_format(self):
        self.assertTrue(
            self.check.check_format("{0,1:C3} strins", "string", False, None)
        )

    def test_wrong_format(self):
        self.assertTrue(
            self.check.check_format("{0} string", "{1} string", False, None)
        )

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format("{0} string", "string", True, None))

    def test_escaping_with_position(self):
        self.assertFalse(self.check.check_format("{{ 0 }}", "string", False, None))

    def test_wrong_attribute_format(self):
        self.assertTrue(
            self.check.check_format("{0} string", "{1} string", False, None)
        )

    def test_reordered_format(self):
        self.assertFalse(
            self.check.check_format("{0} string {1}", "{1} string {0}", False, None)
        )


class JavaFormatCheckTest(CheckTestCase):
    check = JavaFormatCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "java-format",
            "%1s string %2s",
            [(0, 3, "%1s"), (11, 14, "%2s")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_escaping(self):
        self.assertFalse(self.check.check_format("%% s %%", "string", False, None))

    def test_format(self):
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_time_format(self):
        self.assertFalse(
            self.check.check_format("%1$tH strins", "%1$tH string", False, None)
        )

    def test_wrong_position_format(self):
        self.assertTrue(
            self.check.check_format("%s string", "%s string %s", False, None)
        )

    def test_named_format(self):
        self.assertFalse(
            self.check.check_format("%1s string %2s", "%1s string %2s", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("%1s string", "string", False, None))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format("%1$05d string", "string", False, None))

    def test_wrong_argument_format(self):
        self.assertTrue(
            self.check.check_format("%1s string", "%2s string", False, None)
        )

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format("%s strins", "%d string", False, None))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format("%1s string", "string", True, None))

    def test_reordered_format(self):
        self.assertTrue(
            self.check.check_format("%1s string %2d", "%2d string %1s", False, None)
        )


class JavaMessageFormatCheckTest(CheckTestCase):
    check = JavaMessageFormatCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "java-messageformat",
            "{0}string{1}",
            [(0, 3, "{0}"), (9, 12, "{1}")],
        )
        self.unit = MockUnit(source="source")

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, self.unit))

    def test_escaping_no_position(self):
        self.assertFalse(
            self.check.check_format("{{ string }}", "string", False, self.unit)
        )

    def test_simple_format(self):
        self.assertFalse(
            self.check.check_format("{0} strins", "{0} string", False, self.unit)
        )

    def test_format_with_width(self):
        self.assertFalse(
            self.check.check_format("{0,1} strins", "{0,1} string", False, self.unit)
        )

    def test_format_with_flag(self):
        self.assertFalse(
            self.check.check_format("{0:C2} strins", "{0:C2} string", False, self.unit)
        )

    def test_full_format(self):
        self.assertFalse(
            self.check.check_format(
                "{0,1:N0} strins", "{0,1:N0} string", False, self.unit
            )
        )

    def test_missing_format(self):
        self.assertTrue(
            self.check.check_format("{0} strins", "string", False, self.unit)
        )

    def test_missing_type_format(self):
        self.assertTrue(
            self.check.check_format("{0,number} strins", "string", False, self.unit)
        )

    def test_missing_flag_format(self):
        self.assertTrue(
            self.check.check_format("{0} strins", "string", False, self.unit)
        )

    def test_missing_full_format(self):
        self.assertTrue(
            self.check.check_format(
                "{0,number,integer} strins", "string", False, self.unit
            )
        )

    def test_wrong_format(self):
        self.assertTrue(
            self.check.check_format("{0} string", "{1} string", False, self.unit)
        )

    def test_missing_named_format_ignore(self):
        self.assertFalse(
            self.check.check_format("{0} string", "string", True, self.unit)
        )

    def test_escaping_with_position(self):
        self.assertFalse(self.check.check_format("{{ 0 }}", "string", False, self.unit))

    def test_wrong_attribute_format(self):
        self.assertTrue(
            self.check.check_format("{0} string", "{1} string", False, self.unit)
        )

    def test_reordered_format(self):
        self.assertFalse(
            self.check.check_format(
                "{0} string {1}", "{1} string {0}", False, self.unit
            )
        )

    def test_skip(self):
        unit = MockUnit(source="source")
        self.assertTrue(self.check.should_skip(unit))
        unit = MockUnit(source="source", flags="java-messageformat")
        self.assertFalse(self.check.should_skip(unit))
        unit = MockUnit(source="source", flags="auto-java-messageformat")
        self.assertTrue(self.check.should_skip(unit))
        unit = MockUnit(source="{0}", flags="auto-java-messageformat")
        self.assertFalse(self.check.should_skip(unit))

    def test_quotes(self):
        self.assertFalse(
            self.check.check_format(
                "{0} string {1}", "'{1}' strin''g '{0}'", False, self.unit
            )
        )
        self.assertTrue(
            self.check.check_format(
                "{0} string {1}", "'{1}' strin''g '{0}", False, self.unit
            )
        )
        self.assertTrue(
            self.check.check_format(
                "{0} string {1}", "'{1}' strin'g '{0}'", False, self.unit
            )
        )

    def test_description(self):
        unit = Unit(
            source="{0}''s brush is {1} centimeters tall",
            target="{0}'s brush is {1} centimeters tall",
            extra_flags="java-messageformat",
            translation=Translation(
                component=Component(
                    file_format="auto",
                    source_language=Language("en"),
                ),
                language=Language("cs"),
            ),
        )
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "You need to pair up an apostrophe with another one.",
        )


class QtFormatCheckTest(CheckTestCase):
    check = QtFormatCheck()
    flag = "qt-format"

    def setUp(self):
        super().setUp()
        self.test_highlight = (self.flag, "%1string%2", [(0, 2, "%1"), (8, 10, "%2")])

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_simple_format(self):
        self.assertFalse(self.check.check_format("%1 strins", "%1 string", False, None))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("%1 strins", "string", False, None))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format("%1 string", "%2 string", False, None))

    def test_reordered_format(self):
        self.assertFalse(
            self.check.check_format("%1 string %2", "%2 string %1", False, None)
        )

    def test_reused_format(self):
        self.assertFalse(
            self.check.check_format("%1 string %1", "%1 string %1", False, None)
        )


class QtPluralCheckTest(CheckTestCase):
    check = QtPluralCheck()
    flag = "qt-plural-format"

    def setUp(self):
        super().setUp()
        self.test_highlight = (self.flag, "%Lnstring", [(0, 3, "%Ln")])

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_plural_format(self):
        self.assertFalse(
            self.check.check_format("%n string(s)", "%n string", False, None)
        )

    def test_plural_localized_format(self):
        self.assertFalse(
            self.check.check_format("%Ln string(s)", "%Ln string", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("%n string(s)", "string", False, None))


class RubyFormatCheckTest(CheckTestCase):
    check = RubyFormatCheck()
    flag = "ruby-format"

    def test_check_highlight(self):
        self.test_highlight = (self.flag, "%dstring%s", [(0, 2, "%d"), (8, 10, "%s")])
        super().test_check_highlight()

    def test_check_highlight_named(self):
        self.test_highlight = (
            self.flag,
            "%<int>dstring%<str>s",
            [(0, 7, "%<int>d"), (13, 20, "%<str>s")],
        )
        super().test_check_highlight()

    def test_check_highlight_named_template(self):
        self.test_highlight = (
            self.flag,
            "%{int}string%{str}",
            [(0, 6, "%{int}"), (12, 18, "%{str}")],
        )
        super().test_check_highlight()

    def test_check_highlight_complex_named_template(self):
        self.test_highlight = (
            self.flag,
            "%8.8{foo}string%+08.2<float>fstring",
            [(0, 9, "%8.8{foo}"), (15, 29, "%+08.2<float>f")],
        )
        super().test_check_highlight()

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self):
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_space_format(self):
        self.assertTrue(
            self.check.check_format("%d % string", "%d % other", False, None)
        )

    def test_percent_format(self):
        self.assertFalse(
            self.check.check_format("%d%% string", "%d%% string", False, None)
        )

    def test_named_format(self):
        self.assertFalse(
            self.check.check_format("%<name>s string", "%<name>s string", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("%s string", "string", False, None))

    def test_missing_named_format(self):
        self.assertTrue(
            self.check.check_format("%<name>s string", "string", False, None)
        )

    def test_missing_named_format_ignore(self):
        self.assertFalse(
            self.check.check_format("%<name>s string", "string", True, None)
        )

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format("%s string", "%c string", False, None))

    def test_reordered_format(self):
        self.assertTrue(
            self.check.check_format("%s %d string", "%d %s string", False, None)
        )

    def test_wrong_named_format(self):
        self.assertTrue(
            self.check.check_format("%<name>s string", "%<jmeno>s string", False, None)
        )

    def test_reordered_named_format(self):
        self.assertFalse(
            self.check.check_format(
                "%<name>s %<foo>s string",
                "%<foo>s %<name>s string",
                False,
                None,
            )
        )

    def test_reordered_named_format_long(self):
        self.assertFalse(
            self.check.check_format(
                "%<count>d strings into %<languages>d languages %<percent>d%%",
                "%<languages>d dil içinde %<count>d satır %%%<percent>d",
                False,
                None,
            )
        )

    def test_formatting_named_format(self):
        self.assertFalse(
            self.check.check_format(
                "%+08.2<foo>f string", "%+08.2<foo>f string", False, None
            )
        )

    def test_missing_named_template_format(self):
        self.assertTrue(
            self.check.check_format("%{name} string", "string", False, None)
        )

    def test_missing_named_template_format_ignore(self):
        self.assertFalse(
            self.check.check_format("%{name} string", "string", True, None)
        )

    def test_wrong_named_template_format(self):
        self.assertTrue(
            self.check.check_format("%{name} string", "%{jmeno} string", False, None)
        )

    def test_reordered_named_template_format(self):
        self.assertFalse(
            self.check.check_format(
                "%{name} %{foo} string",
                "%{foo} %{name} string",
                False,
                None,
            )
        )

    def test_formatting_named_template_format(self):
        self.assertFalse(
            self.check.check_format("%8.8{foo} string", "%8.8{foo} string", False, None)
        )

    def test_reordered_named_template_format_long(self):
        self.assertFalse(
            self.check.check_format(
                "%{count} strings into %{languages} languages %{percent}%%",
                "%{languages} dil içinde %{count} satır %%%{percent}",
                False,
                None,
            )
        )


class PluralTest(FixtureTestCase):
    check = PythonFormatCheck()

    def do_check(self, sources, targets, translation):
        return self.check.check_target_unit(
            sources,
            targets,
            Unit(
                translation=translation,
                source=join_plural(sources),
                target=join_plural(targets),
            ),
        )

    def test_arabic(self):
        arabic = Language.objects.get(code="ar")
        translation = Translation(language=arabic, plural=arabic.plural)
        # Singular, correct format string
        self.assertFalse(self.do_check(["hello %s"], ["hell %s"], translation))
        # Singular, missing format string
        self.assertTrue(self.do_check(["hello %s"], ["hell"], translation))
        # Plural, correct format string
        self.assertFalse(self.do_check(["hello %s"] * 2, ["hell %s"] * 6, translation))
        # Plural, missing format string
        self.assertTrue(self.do_check(["hello %s"] * 2, ["hell"] * 6, translation))
        # Plural, correct format string (missing on single value plurals)
        self.assertFalse(
            self.do_check(
                ["hello %s"] * 2, ["hell"] * 3 + ["hello %s"] * 3, translation
            )
        )
        # Plural, missing format string on multi value plural
        self.assertTrue(
            self.do_check(
                ["hello %s"] * 2, ["hell"] * 4 + ["hello %s"] * 2, translation
            )
        )

    def test_non_format_singular(self):
        czech = Language.objects.get(code="cs")
        translation = Translation(language=czech, plural=czech.plural)
        self.assertFalse(
            self.do_check(
                ["One apple", "%d apples"],
                ["%d jablko", "%d jablka", "%d jablek"],
                translation,
            )
        )
        self.assertFalse(
            self.do_check(
                ["One apple", "%d apples"],
                ["Jedno jablko", "%d jablka", "%d jablek"],
                translation,
            )
        )
        self.assertTrue(
            self.do_check(
                ["One apple", "%d apples"],
                ["Jedno jablko", "jablka", "%d jablek"],
                translation,
            )
        )

    def test_non_format_singular_named(self):
        language = Language.objects.get(code="cs")
        translation = Translation(language=language, plural=language.plural)
        self.assertFalse(
            self.do_check(
                ["One apple", "%(count)s apples"],
                ["%(count)s jablko", "%(count)s jablka", "%(count)s jablek"],
                translation,
            )
        )
        self.assertFalse(
            self.do_check(
                ["One apple", "%(count)s apples"],
                ["Jedno jablko", "%(count)s jablka", "%(count)s jablek"],
                translation,
            )
        )
        self.assertTrue(
            self.do_check(
                ["One apple", "%(count)s apples"],
                ["Jedno jablko", "jablka", "%(count)s jablek"],
                translation,
            )
        )

    def test_non_format_singular_named_be(self):
        language = Language.objects.get(code="be")
        translation = Translation(language=language, plural=language.plural)
        self.assertTrue(
            self.do_check(
                ["One apple", "%(count)s apples"],
                ["Jedno jablko", "%(count)s jablka", "%(count)s jablek"],
                translation,
            )
        )

    def test_non_format_singular_named_kab(self):
        language = Language.objects.get(code="kab")
        translation = Translation(language=language, plural=language.plural)
        self.assertFalse(
            self.do_check(
                ["One apple", "%(count)s apples"],
                ["Jedno jablko", "%(count)s jablka", "%(count)s jablek"],
                translation,
            )
        )

    def test_french_singular(self):
        language = Language.objects.get(code="fr")
        translation = Translation(language=language, plural=language.plural)
        self.assertFalse(
            self.do_check(
                ["One apple", "%(count)s apples"],
                ["Jedno jablko", "%(count)s jablek"],
                translation,
            )
        )
        self.assertFalse(
            self.do_check(
                ["%(count)s apple", "%(count)s apples"],
                ["%(count)s jablko", "%(count)s jablek"],
                translation,
            )
        )
        self.assertFalse(
            self.do_check(
                ["One apple", "%(count)s apples"],
                ["%(count)s jablko", "%(count)s jablek"],
                translation,
            )
        )
        self.assertFalse(
            self.do_check(
                ["%(count)s apple", "%(count)s apples"],
                ["Jedno jablko", "%(count)s jablek"],
                translation,
            )
        )


class I18NextInterpolationCheckTest(CheckTestCase):
    check = I18NextInterpolationCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "i18next-interpolation",
            "{{foo}} string {{bar}}",
            [(0, 7, "{{foo}}"), (15, 22, "{{bar}}")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self):
        self.assertFalse(
            self.check.check_format("{{foo}} string", "{{foo}} string", False, None)
        )
        self.assertFalse(
            self.check.check_format("{{ foo }} string", "{{ foo }} string", False, None)
        )
        self.assertFalse(
            self.check.check_format("{{ foo }} string", "{{foo}} string", False, None)
        )

    def test_nesting(self):
        self.assertFalse(
            self.check.check_format("$t(bar) string", "$t(bar) other", False, None)
        )
        self.assertFalse(
            self.check.check_format("$t( bar ) string", "$t( bar ) other", False, None)
        )
        self.assertFalse(
            self.check.check_format("$t( bar ) string", "$t(bar) other", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(
            self.check.check_format("{{foo}} string", "string", False, None)
        )

    def test_missing_nesting(self):
        self.assertTrue(self.check.check_format("$t(bar) string", "other", False, None))

    def test_wrong_format(self):
        self.assertTrue(
            self.check.check_format("{{foo}} string", "{{bar}} string", False, None)
        )


class ESTemplateLiteralsCheckTest(CheckTestCase):
    check = ESTemplateLiteralsCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "es-format",
            "${foo} string ${bar}",
            [(0, 6, "${foo}"), (14, 20, "${bar}")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self):
        self.assertFalse(
            self.check.check_format("${foo} string", "${foo} string", False, None)
        )
        self.assertFalse(
            self.check.check_format("${ foo } string", "${ foo } string", False, None)
        )
        self.assertFalse(
            self.check.check_format("${ foo } string", "${foo} string", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("${foo} string", "string", False, None))

    def test_wrong_format(self):
        self.assertTrue(
            self.check.check_format("${foo} string", "${bar} string", False, None)
        )

    def test_description(self):
        unit = Unit(
            source="${foo}",
            target="${bar}",
            extra_flags="es-format",
        )
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "Following format strings are missing: ${foo}<br />"
            "Following format strings are extra: ${bar}",
        )


class PercentPlaceholdersCheckTest(CheckTestCase):
    check = PercentPlaceholdersCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "percent-placeholders",
            "%foo% string %bar%",
            [(0, 5, "%foo%"), (13, 18, "%bar%")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self):
        self.assertFalse(
            self.check.check_format("%foo% string", "%foo% string", False, None)
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("%foo% string", "string", False, None))

    def test_wrong_format(self):
        self.assertTrue(
            self.check.check_format("%foo% string", "%bar% string", False, None)
        )


class VueFormattingCheckTest(CheckTestCase):
    check = VueFormattingCheck()

    def setUp(self):
        super().setUp()
        self.test_highlight = (
            "vue-format",
            "{foo} string %{bar}",
            [(0, 5, "{foo}"), (13, 19, "%{bar}")],
        )

    def test_no_format(self):
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self):
        self.assertFalse(
            self.check.check_format("%{foo} string", "%{foo} string", False, None)
        )
        self.assertFalse(
            self.check.check_format("{foo} string", "{foo} string", False, None)
        )
        self.assertFalse(
            self.check.check_format(
                "@.lower:message.homeAddress string",
                "@.lower:message.homeAddress string",
                False,
                None,
            )
        )
        self.assertFalse(
            self.check.check_format(
                "@:message.the_world string",
                "@:message.the_world string",
                False,
                None,
            )
        )
        self.assertFalse(
            self.check.check_format(
                "@:(message.dio) string",
                "@:(message.dio) string",
                False,
                None,
            )
        )

    def test_missing_format(self):
        self.assertTrue(self.check.check_format("%{foo} string", "string", False, None))
        self.assertTrue(self.check.check_format("{foo} string", "string", False, None))
        self.assertTrue(
            self.check.check_format(
                "@.lower:message.homeAddress string",
                "string",
                False,
                None,
            )
        )
        self.assertTrue(
            self.check.check_format("@:message.the_world string", "string", False, None)
        )
        self.assertTrue(
            self.check.check_format("@:(message.dio) string", "string", False, None)
        )

    def test_wrong_format(self):
        self.assertTrue(
            self.check.check_format("%{foo} string", "%{bar} string", False, None)
        )
        self.assertTrue(
            self.check.check_format("{foo} string", "{bar} string", False, None)
        )


class MultipleUnnamedFormatsCheckTestCase(SimpleTestCase):
    check = MultipleUnnamedFormatsCheck()

    def test_none_flag(self):
        self.assertFalse(self.check.check_source(["text"], MockUnit()))

    def test_none_format(self):
        self.assertFalse(self.check.check_source(["text"], MockUnit(flags="c-format")))

    def test_good(self):
        self.assertFalse(
            self.check.check_source(["%1$s %2$s"], MockUnit(flags="c-format"))
        )

    def test_bad_c(self):
        self.assertTrue(self.check.check_source(["%s %s"], MockUnit(flags="c-format")))

    def test_bad_python(self):
        self.assertTrue(
            self.check.check_source(["{} {}"], MockUnit(flags="python-brace-format"))
        )

    def test_good_multi_format(self):
        self.assertFalse(
            self.check.check_source(
                ["Test %s"], MockUnit(flags="c-format,python-format")
            )
        )
