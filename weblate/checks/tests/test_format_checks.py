# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for quality checks."""

from __future__ import annotations

from django.test import SimpleTestCase

from weblate.checks.format import (
    AutomatticComponentsCheck,
    BaseFormatCheck,
    CFormatCheck,
    CSharpFormatCheck,
    ESTemplateLiteralsCheck,
    I18NextInterpolationCheck,
    JavaFormatCheck,
    JavaMessageFormatCheck,
    LuaFormatCheck,
    MultipleUnnamedFormatsCheck,
    ObjectPascalFormatCheck,
    PercentPlaceholdersCheck,
    PerlBraceFormatCheck,
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
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.util import join_plural


class PythonFormatCheckTest(CheckTestCase):
    check: BaseFormatCheck = PythonFormatCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "python-format",
            "%sstring%d",
            [(0, 2, "%s"), (8, 10, "%d")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_space_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%d % string", "%d % other", False, None)
        )

    def test_percent_format(self) -> None:
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

    def test_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%(name)s string", "%(name)s string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "string", False, None))

    def test_missing_named_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%(name)s string", "string", False, None)
        )

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(
            self.check.check_format("%(name)s string", "string", True, None)
        )

    def test_wrong_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "%c string", False, None))

    def test_reordered_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%s %d string", "%d %s string", False, None)
        )

    def test_wrong_named_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%(name)s string", "%(jmeno)s string", False, None)
        )

    def test_reordered_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "%(name)s %(foo)s string", "%(foo)s %(name)s string", False, None
            )
        )

    def test_reordered_named_format_long(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "%(count)d strings into %(languages)d languages %(percent)d%%",
                "%(languages)d dil içinde %(count)d satır %%%(percent)d",
                False,
                None,
            )
        )

    def test_feedback(self) -> None:
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

    def test_description(self) -> None:
        unit = Unit(
            source="%(count)d",
            target="%(languages)d",
            extra_flags="python-format",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language(code="en"),
                    project=Project(),
                )
            ),
        )
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following format strings are missing:
            <span class="hlcheck" data-value="%(count)d">%(count)d</span>
            <br />
            The following format strings are extra:
            <span class="hlcheck" data-value="%(languages)d">%(languages)d</span>
            """,
        )

    def test_description_nolocation(self) -> None:
        unit = Unit(
            source="%d %s",
            target="%s %d",
            extra_flags="python-format",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language(code="en"),
                    project=Project(),
                )
            ),
        )
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "The following format strings are in the wrong order: %d, %s",
        )

    def test_duplicated_format(self) -> None:
        self.assertEqual(
            self.check.check_format(
                "%(LANGUAGE)s %(classF)s %(mailto)s %(classS)s %(mail)s",  # codespell:ignore
                "%(classF)s %(LANGUAGE)s %(classF)s %(mailto)s %(classS)s %(mail)s",  # codespell:ignore
                False,
                None,
            ),
            {"missing": [], "extra": ["(classF)s"]},
        )
        self.assertEqual(
            self.check.check_format(
                "%(test)s%(test)s%(test)s%(test)s",
                "%(test)s%(test)s%(test)s",
                False,
                None,
            ),
            {"missing": ["(test)s"], "extra": []},
        )


class PHPFormatCheckTest(CheckTestCase):
    check = PHPFormatCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "php-format",
            "%sstring%d",
            [(0, 2, "%s"), (8, 10, "%d")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%1$s string", "%1$s string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "string", False, None))

    def test_missing_named_format(self) -> None:
        self.assertTrue(self.check.check_format("%1$s string", "string", False, None))

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(self.check.check_format("%1$s string", "string", True, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "%c string", False, None))

    def test_double_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%s string", "%s%s string", False, None)
        )

    def test_reorder_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%1$s %2$s string", "%2$s %1$s string", False, None)
        )

    def test_wrong_named_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%1$s string", "%s string", False, None)
        )

    def test_wrong_percent_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%s%% (0.1%%)", "%s%% (0.1%x)", False, None)
        )

    def test_missing_percent_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%s%% %%", "%s%% percent", False, None)
        )

    def test_space_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%d % string", "%d % other", False, None)
        )


class SchemeFormatCheckTest(CheckTestCase):
    check = SchemeFormatCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "scheme-format",
            "~sstring~d",
            [(0, 2, "~s"), (8, 10, "~d")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(self.check.check_format("~s string", "~s string", False, None))

    def test_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format("~0@*~s string", "~0@*~s string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("~s string", "string", False, None))

    def test_missing_named_format(self) -> None:
        self.assertTrue(self.check.check_format("~1@*~s string", "string", False, None))

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(self.check.check_format("~1@*~s string", "string", True, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(self.check.check_format("~s string", "~c string", False, None))

    def test_double_format(self) -> None:
        self.assertTrue(
            self.check.check_format("~s string", "~s~s string", False, None)
        )

    def test_reorder_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "~1@*~s ~2@*~s string", "~2@*~s ~1@*~s string", False, None
            )
        )

    def test_wrong_named_format(self) -> None:
        self.assertTrue(
            self.check.check_format("~1@*~s string", "~s string", False, None)
        )

    def test_wrong_tilde_format(self) -> None:
        self.assertTrue(
            self.check.check_format("~s~~ (0.1~~)", "~s~~ (0.1~x)", False, None)
        )

    def test_missing_tilde_format(self) -> None:
        self.assertFalse(self.check.check_format("~s~~ ~~", "~s~~ tilde", False, None))


class CFormatCheckTest(CheckTestCase):
    check: BaseFormatCheck = CFormatCheck()
    flag = "c-format"

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (self.flag, "%sstring%d", [(0, 2, "%s"), (8, 10, "%d")])

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%10s string", "%10s string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "string", False, None))

    def test_missing_named_format(self) -> None:
        self.assertTrue(self.check.check_format("%10s string", "string", False, None))

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(self.check.check_format("%10s string", "string", True, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "%c string", False, None))

    def test_wrong_named_format(self) -> None:
        self.assertEqual(
            self.check.check_format("%10s string", "%20s string", False, None),
            {"missing": ["10s"], "extra": ["20s"]},
        )

    def test_reorder_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%1$s %2$s string", "%2$s %1$s string", False, None)
        )

    def test_locale_delimiter(self) -> None:
        self.assertFalse(
            self.check.check_format("lines: %6.3f", "radky: %'6.3f", False, None)
        )

    def test_ld_format(self) -> None:
        self.assertEqual(
            self.check.check_format(
                "%ld bytes (free %ld bytes, used %ld bytes)",
                "%l octets (%l octets libres, %l octets utilisés)",
                True,
                None,
            ),
            {"missing": ["ld", "ld", "ld"], "extra": ["l", "l", "l"]},
        )

    def test_parenthesis(self) -> None:
        self.assertFalse(self.check.check_format("(%.0lf%%)", "(%%%.0lf)", False, None))


class LuaFormatCheckTest(CFormatCheckTest):
    check = LuaFormatCheck()
    flag = "lua-format"


class ObjectPascalFormatCheckTest(CheckTestCase):
    check = ObjectPascalFormatCheck()
    flag = "object-pascal-format"

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            self.flag,
            "%-9sstring%d",
            [(0, 4, "%-9s"), (10, 12, "%d")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_width_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%10s string", "%10s string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "string", False, None))

    def test_added_format(self) -> None:
        self.assertTrue(self.check.check_format("string", "%s string", False, None))

    def test_missing_width_format(self) -> None:
        self.assertTrue(self.check.check_format("%10s string", "string", False, None))

    def test_missing_width_format_ignore(self) -> None:
        self.assertFalse(self.check.check_format("%10s string", "string", True, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "%d string", False, None))

    def test_invalid_format(self) -> None:
        self.assertTrue(self.check.check_format("%d string", "%c string", False, None))

    def test_looks_like_format(self) -> None:
        self.assertFalse(self.check.check_format("%c string", "%c string", False, None))

    def test_percent_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%6.2f%% string", "%6.2f%% string", False, None)
        )

    def test_wrong_digits(self) -> None:
        self.assertTrue(
            self.check.check_format("%6.2f string", "%5.3f string", False, None)
        )

    def test_wrong_wildcard(self) -> None:
        self.assertTrue(
            self.check.check_format("%*s string", "%10s string", False, None)
        )

    def test_reorder_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%1:s %2:d string", "%2:d %1:s string", False, None)
        )


class PerlFormatCheckTest(CFormatCheckTest):
    check = PerlFormatCheck()
    flag = "perl-format"


class PerlBraceFormatCheckTest(CheckTestCase):
    check = PerlBraceFormatCheck()
    flag = "perl-brace-format"

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            self.flag,
            "{x}string{y}",
            [(0, 3, "{x}"), (9, 12, "{y}")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("string", "string", False, None))

    def test_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format("{x} string {y}", "{x} string {y}", False, None)
        )

    def test_wrong_position_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{x} string", "{x} string {y}", False, None)
        )

    def test_missing_named_format(self) -> None:
        self.assertTrue(self.check.check_format("{x} string", "string", False, None))

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(self.check.check_format("{x} string", "string", True, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{x} string", "{y} string", False, None)
        )

    def test_wrong_named_format(self) -> None:
        self.assertEqual(
            self.check.check_format("{x} string", "{y} string", False, None),
            {"missing": ["{x}"], "extra": ["{y}"]},
        )

    def test_description(self) -> None:
        unit = Unit(
            source="{foo}",
            target="{bar}",
            extra_flags="es-format",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language(code="en"),
                    project=Project(),
                )
            ),
        )
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following format strings are missing:
            <span class="hlcheck" data-value="{foo}">{foo}</span>
            <br />
            The following format strings are extra:
            <span class="hlcheck" data-value="{bar}">{bar}</span>
            """,
        )


class PythonBraceFormatCheckTest(CheckTestCase):
    check = PythonBraceFormatCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "python-brace-format",
            "{0}string{1}",
            [(0, 3, "{0}"), (9, 12, "{1}")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_position_format(self) -> None:
        self.assertFalse(
            self.check.check_format("{} string {}", "{} string {}", False, None)
        )

    def test_wrong_position_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{} string", "{} string {}", False, None)
        )

    def test_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format("{s1} string {s2}", "{s1} string {s2}", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("{} string", "string", False, None))

    def test_missing_named_format(self) -> None:
        self.assertTrue(self.check.check_format("{s1} string", "string", False, None))

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(self.check.check_format("{s} string", "string", True, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{s} string", "{c} string", False, None)
        )

    def test_escaping(self) -> None:
        self.assertFalse(self.check.check_format("{{ string }}", "string", False, None))
        self.assertFalse(
            self.check.check_format("{{ string }}", "{{ string }}", False, None)
        )

    def test_attribute_format(self) -> None:
        self.assertFalse(
            self.check.check_format("{s.foo} string", "{s.foo} string", False, None)
        )

    def test_wrong_attribute_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{s.foo} string", "{s.bar} string", False, None)
        )

    def test_extra_close_bracket(self) -> None:
        self.assertTrue(
            self.check.check_format("{s} string", "{s}} string", False, None)
        )

    def test_extra_open_bracket(self) -> None:
        self.assertTrue(
            self.check.check_format("{s} string", "{ {s} string", False, None)
        )

    def test_extra_open_bracket_extra(self) -> None:
        self.assertTrue(self.check.check_format("string", "{ {s} string", False, None))

    def test_wrong_order(self) -> None:
        self.assertTrue(self.check.check_format("string", "}s{ string", False, None))

    def test_escape_bracket(self) -> None:
        self.assertFalse(
            self.check.check_format("{{ {{ {s} }}", "{{ {{ {s} }}", False, None)
        )

    def test_description(self) -> None:
        unit = Unit(
            source="{s} {a}",
            target="a a",
            extra_flags="python-brace-format",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language("en"),
                    project=Project(),
                )
            ),
        )
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following format strings are missing:
            <span class="hlcheck" data-value="{a}">{a}</span>,
            <span class="hlcheck" data-value="{s}">{s}</span>
            """,
        )

    def test_description_braces(self) -> None:
        unit = Unit(
            source="{s}",
            target="{ {s} }",
            extra_flags="python-brace-format",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language("en"),
                    project=Project(),
                )
            ),
        )
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            Single <span class="hlcheck" data-value="{">{</span> encountered in the format string.<br>
            Single <span class="hlcheck" data-value="}">}</span> encountered in the format string.
            """,
        )


class CSharpFormatCheckTest(CheckTestCase):
    check = CSharpFormatCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "c-sharp-format",
            "{0}string{1}",
            [(0, 3, "{0}"), (9, 12, "{1}")],
        )
        self.test_failure_1 = ("{0} string", "0 string", "c-sharp-format")
        self.test_failure_2 = ("{0} string", "0 string", "csharp-format")

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_escaping_no_position(self) -> None:
        self.assertFalse(self.check.check_format("{{ string }}", "string", False, None))

    def test_simple_format(self) -> None:
        self.assertFalse(
            self.check.check_format("{0} strins", "{0} string", False, None)
        )

    def test_format_with_width(self) -> None:
        self.assertFalse(
            self.check.check_format("{0,1} strins", "{0,1} string", False, None)
        )

    def test_format_with_flag(self) -> None:
        self.assertFalse(
            self.check.check_format("{0:C2} strins", "{0:C2} string", False, None)
        )

    def test_full_format(self) -> None:
        self.assertFalse(
            self.check.check_format("{0,1:N0} strins", "{0,1:N0} string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("{0} strins", "string", False, None))

    def test_missing_width_format(self) -> None:
        self.assertTrue(self.check.check_format("{0,1} strins", "string", False, None))

    def test_missing_flag_format(self) -> None:
        self.assertTrue(self.check.check_format("{0:C1} strins", "string", False, None))

    def test_missing_full_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{0,1:C3} strins", "string", False, None)
        )

    def test_wrong_format(self) -> None:
        self.assertEqual(
            self.check.check_format("{0} string", "{1} string", False, None),
            {"missing": ["0"], "extra": ["1"]},
        )

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(self.check.check_format("{0} string", "string", True, None))

    def test_escaping_with_position(self) -> None:
        self.assertFalse(self.check.check_format("{{ 0 }}", "string", False, None))

    def test_wrong_attribute_format(self) -> None:
        self.assertEqual(
            self.check.check_format("{0} string", "{1} string", False, None),
            {"missing": ["0"], "extra": ["1"]},
        )

    def test_reordered_format(self) -> None:
        self.assertFalse(
            self.check.check_format("{0} string {1}", "{1} string {0}", False, None)
        )


class JavaFormatCheckTest(CheckTestCase):
    check = JavaFormatCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "java-printf-format",
            "%1s string %2s",
            [(0, 3, "%1s"), (11, 14, "%2s")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_escaping(self) -> None:
        self.assertFalse(self.check.check_format("%% s %%", "string", False, None))

    def test_escaping_translation(self) -> None:
        self.assertFalse(
            self.check.check_format("Something failed", "Something %%s", False, None)
        )

    def test_format(self) -> None:
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_time_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%1$tH strins", "%1$tH string", False, None)
        )

    def test_wrong_position_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%s string", "%s string %s", False, None)
        )

    def test_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%1s string %2s", "%1s string %2s", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("%1s string", "string", False, None))

    def test_missing_named_format(self) -> None:
        self.assertTrue(self.check.check_format("%1$05d string", "string", False, None))

    def test_wrong_argument_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%1s string", "%2s string", False, None)
        )

    def test_wrong_format(self) -> None:
        self.assertTrue(self.check.check_format("%s strins", "%d string", False, None))

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(self.check.check_format("%1s string", "string", True, None))

    def test_reordered_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%1s string %2d", "%2d string %1s", False, None)
        )


class JavaMessageFormatCheckTest(CheckTestCase):
    check = JavaMessageFormatCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "java-format",
            "{0}string{1}",
            [(0, 3, "{0}"), (9, 12, "{1}")],
        )
        self.unit = MockUnit(source="source")

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, self.unit))

    def test_escaping_no_position(self) -> None:
        self.assertFalse(
            self.check.check_format("{{ string }}", "string", False, self.unit)
        )

    def test_simple_format(self) -> None:
        self.assertFalse(
            self.check.check_format("{0} strins", "{0} string", False, self.unit)
        )

    def test_format_with_width(self) -> None:
        self.assertFalse(
            self.check.check_format("{0,1} strins", "{0,1} string", False, self.unit)
        )

    def test_format_with_flag(self) -> None:
        self.assertFalse(
            self.check.check_format("{0:C2} strins", "{0:C2} string", False, self.unit)
        )

    def test_full_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "{0,1:N0} strins", "{0,1:N0} string", False, self.unit
            )
        )

    def test_missing_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{0} strins", "string", False, self.unit)
        )

    def test_missing_type_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{0,number} strins", "string", False, self.unit)
        )

    def test_missing_flag_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{0} strins", "string", False, self.unit)
        )

    def test_missing_full_format(self) -> None:
        self.assertTrue(
            self.check.check_format(
                "{0,number,integer} strins", "string", False, self.unit
            )
        )

    def test_wrong_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{0} string", "{1} string", False, self.unit)
        )

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(
            self.check.check_format("{0} string", "string", True, self.unit)
        )

    def test_escaping_with_position(self) -> None:
        self.assertFalse(self.check.check_format("{{ 0 }}", "string", False, self.unit))

    def test_wrong_attribute_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{0} string", "{1} string", False, self.unit)
        )

    def test_reordered_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "{0} string {1}", "{1} string {0}", False, self.unit
            )
        )

    def test_skip(self) -> None:
        unit = MockUnit(source="source")
        self.assertTrue(self.check.should_skip(unit))
        unit = MockUnit(source="source", flags="java-format")
        self.assertFalse(self.check.should_skip(unit))
        unit = MockUnit(source="source", flags="auto-java-messageformat")
        self.assertTrue(self.check.should_skip(unit))
        unit = MockUnit(source="{0}", flags="auto-java-messageformat")
        self.assertFalse(self.check.should_skip(unit))
        unit = MockUnit(
            source="{0}", flags="auto-java-messageformat,ignore-java-format"
        )
        self.assertTrue(self.check.should_skip(unit))

    def test_quotes(self) -> None:
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

    def test_description(self) -> None:
        unit = Unit(
            source="{0}''s brush is {1} centimeters tall",
            target="{0}'s brush is {1} centimeters tall",
            extra_flags="java-format",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language("en"),
                    project=Project(),
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

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (self.flag, "%1string%2", [(0, 2, "%1"), (8, 10, "%2")])

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_simple_format(self) -> None:
        self.assertFalse(self.check.check_format("%1 strins", "%1 string", False, None))

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("%1 strins", "string", False, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(self.check.check_format("%1 string", "%2 string", False, None))

    def test_reordered_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%1 string %2", "%2 string %1", False, None)
        )

    def test_reused_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%1 string %1", "%1 string %1", False, None)
        )


class QtPluralCheckTest(CheckTestCase):
    check = QtPluralCheck()
    flag = "qt-plural-format"

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (self.flag, "%Lnstring", [(0, 3, "%Ln")])

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_plural_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%n string(s)", "%n string", False, None)
        )

    def test_plural_localized_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%Ln string(s)", "%Ln string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("%n string(s)", "string", False, None))


class RubyFormatCheckTest(CheckTestCase):
    check = RubyFormatCheck()
    flag = "ruby-format"

    def test_check_highlight(self) -> None:
        self.test_highlight = (self.flag, "%dstring%s", [(0, 2, "%d"), (8, 10, "%s")])
        super().test_check_highlight()

    def test_check_highlight_named(self) -> None:
        self.test_highlight = (
            self.flag,
            "%<int>dstring%<str>s",
            [(0, 7, "%<int>d"), (13, 20, "%<str>s")],
        )
        super().test_check_highlight()

    def test_check_highlight_named_template(self) -> None:
        self.test_highlight = (
            self.flag,
            "%{int}string%{str}",
            [(0, 6, "%{int}"), (12, 18, "%{str}")],
        )
        super().test_check_highlight()

    def test_check_highlight_complex_named_template(self) -> None:
        self.test_highlight = (
            self.flag,
            "%8.8{foo}string%+08.2<float>fstring",
            [(0, 9, "%8.8{foo}"), (15, 29, "%+08.2<float>f")],
        )
        super().test_check_highlight()

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(self.check.check_format("%s string", "%s string", False, None))

    def test_space_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%d % string", "%d % other", False, None)
        )

    def test_percent_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%d%% string", "%d%% string", False, None)
        )

    def test_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%<name>s string", "%<name>s string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "string", False, None))

    def test_missing_named_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%<name>s string", "string", False, None)
        )

    def test_missing_named_format_ignore(self) -> None:
        self.assertFalse(
            self.check.check_format("%<name>s string", "string", True, None)
        )

    def test_wrong_format(self) -> None:
        self.assertTrue(self.check.check_format("%s string", "%c string", False, None))

    def test_reordered_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%s %d string", "%d %s string", False, None)
        )

    def test_wrong_named_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%<name>s string", "%<jmeno>s string", False, None)
        )

    def test_reordered_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "%<name>s %<foo>s string",
                "%<foo>s %<name>s string",
                False,
                None,
            )
        )

    def test_reordered_named_format_long(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "%<count>d strings into %<languages>d languages %<percent>d%%",
                "%<languages>d dil içinde %<count>d satır %%%<percent>d",
                False,
                None,
            )
        )

    def test_formatting_named_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "%+08.2<foo>f string", "%+08.2<foo>f string", False, None
            )
        )

    def test_missing_named_template_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%{name} string", "string", False, None)
        )

    def test_missing_named_template_format_ignore(self) -> None:
        self.assertFalse(
            self.check.check_format("%{name} string", "string", True, None)
        )

    def test_wrong_named_template_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%{name} string", "%{jmeno} string", False, None)
        )

    def test_reordered_named_template_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "%{name} %{foo} string",
                "%{foo} %{name} string",
                False,
                None,
            )
        )

    def test_formatting_named_template_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%8.8{foo} string", "%8.8{foo} string", False, None)
        )

    def test_reordered_named_template_format_long(self) -> None:
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

    def do_check(
        self, sources: list[str], targets: list[str], translation, flags: str = ""
    ):
        return self.check.check_target_unit(
            sources,
            targets,
            Unit(
                translation=translation,
                source=join_plural(sources),
                target=join_plural(targets),
                extra_flags=flags,
            ),
        )

    def test_arabic(self) -> None:
        arabic = Language.objects.get(code="ar")
        translation = Translation(
            language=arabic,
            plural=arabic.plural,
            component=Component(
                file_format="po",
                source_language=Language("en"),
                project=Project(),
            ),
        )
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

    def test_arabic_strict(self) -> None:
        arabic = Language.objects.get(code="ar")
        translation = Translation(
            language=arabic,
            plural=arabic.plural,
            component=Component(
                file_format="po",
                source_language=Language("en"),
                project=Project(),
            ),
        )
        self.assertTrue(
            self.do_check(
                ["hello %s"] * 2,
                ["hell"] * 3 + ["hello %s"] * 3,
                translation,
                "strict-format",
            )
        )
        self.assertFalse(
            self.do_check(
                ["hello %s"] * 2, ["hell %s"] * 6, translation, "strict-format"
            )
        )

    def test_non_format_singular_fa(self) -> None:
        czech = Language.objects.get(code="fa")
        translation = Translation(
            language=czech,
            plural=czech.plural,
            component=Component(
                file_format="po",
                source_language=Language("en"),
                project=Project(),
            ),
        )
        self.assertFalse(
            self.do_check(
                ["One apple", "%d apples"],
                ["Jedno jablko", "%d jablka"],
                translation,
            )
        )
        translation = Translation(
            language=czech,
            plural=czech.plural,
            component=Component(
                file_format="aresource",
                source_language=Language("en"),
                project=Project(),
            ),
        )
        self.assertTrue(
            self.do_check(
                ["One apple", "%d apples"],
                ["Jedno jablko", "%d jablka"],
                translation,
            )
        )

    def test_non_format_singular(self) -> None:
        czech = Language.objects.get(code="cs")
        translation = Translation(
            language=czech,
            plural=czech.plural,
            component=Component(
                file_format="po",
                source_language=Language("en"),
                project=Project(),
            ),
        )
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

    def test_non_format_singular_named(self) -> None:
        language = Language.objects.get(code="cs")
        translation = Translation(
            language=language,
            plural=language.plural,
            component=Component(
                file_format="po",
                source_language=Language("en"),
                project=Project(),
            ),
        )
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

    def test_non_format_singular_named_be(self) -> None:
        language = Language.objects.get(code="be")
        translation = Translation(
            language=language,
            plural=language.plural,
            component=Component(
                file_format="po",
                source_language=Language("en"),
                project=Project(),
            ),
        )
        self.assertTrue(
            self.do_check(
                ["One apple", "%(count)s apples"],
                ["Jedno jablko", "%(count)s jablka", "%(count)s jablek"],
                translation,
            )
        )

    def test_non_format_singular_named_kab(self) -> None:
        language = Language.objects.get(code="kab")
        translation = Translation(
            language=language,
            plural=language.plural,
            component=Component(
                file_format="po",
                source_language=Language("en"),
                project=Project(),
            ),
        )
        self.assertFalse(
            self.do_check(
                ["One apple", "%(count)s apples"],
                ["Jedno jablko", "%(count)s jablka", "%(count)s jablek"],
                translation,
            )
        )

    def test_french_singular(self) -> None:
        language = Language.objects.get(code="fr")
        translation = Translation(
            language=language,
            plural=language.plural,
            component=Component(
                file_format="po",
                source_language=Language("en"),
                project=Project(),
            ),
        )
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

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "i18next-interpolation",
            "{{foo}} string {{bar}}",
            [(0, 7, "{{foo}}"), (15, 22, "{{bar}}")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(
            self.check.check_format("{{foo}} string", "{{foo}} string", False, None)
        )
        self.assertFalse(
            self.check.check_format("{{ foo }} string", "{{ foo }} string", False, None)
        )
        self.assertFalse(
            self.check.check_format("{{ foo }} string", "{{foo}} string", False, None)
        )

    def test_nesting(self) -> None:
        self.assertFalse(
            self.check.check_format("$t(bar) string", "$t(bar) other", False, None)
        )
        self.assertFalse(
            self.check.check_format("$t( bar ) string", "$t( bar ) other", False, None)
        )
        self.assertFalse(
            self.check.check_format("$t( bar ) string", "$t(bar) other", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{{foo}} string", "string", False, None)
        )

    def test_missing_nesting(self) -> None:
        self.assertTrue(self.check.check_format("$t(bar) string", "other", False, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{{foo}} string", "{{bar}} string", False, None)
        )


class ESTemplateLiteralsCheckTest(CheckTestCase):
    check = ESTemplateLiteralsCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "es-format",
            "${foo} string ${bar}",
            [(0, 6, "${foo}"), (14, 20, "${bar}")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(
            self.check.check_format("${foo} string", "${foo} string", False, None)
        )
        self.assertFalse(
            self.check.check_format("${ foo } string", "${ foo } string", False, None)
        )
        self.assertFalse(
            self.check.check_format("${ foo } string", "${foo} string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("${foo} string", "string", False, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(
            self.check.check_format("${foo} string", "${bar} string", False, None)
        )

    def test_description(self) -> None:
        unit = Unit(
            source="${foo}",
            target="${bar}",
            extra_flags="es-format",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language("en"),
                    project=Project(),
                )
            ),
        )
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following format strings are missing:
            <span class="hlcheck" data-value="${foo}">${foo}</span>
            <br />
            The following format strings are extra:
            <span class="hlcheck" data-value="${bar}">${bar}</span>
            """,
        )


class PercentPlaceholdersCheckTest(CheckTestCase):
    check = PercentPlaceholdersCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "percent-placeholders",
            "%foo% string %bar%",
            [(0, 5, "%foo%"), (13, 18, "%bar%")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(
            self.check.check_format("%foo% string", "%foo% string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(self.check.check_format("%foo% string", "string", False, None))

    def test_wrong_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%foo% string", "%bar% string", False, None)
        )


class VueFormattingCheckTest(CheckTestCase):
    check = VueFormattingCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "vue-format",
            "{foo} string %{bar}",
            [(0, 5, "{foo}"), (13, 19, "%{bar}")],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
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

    def test_missing_format(self) -> None:
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

    def test_wrong_format(self) -> None:
        self.assertTrue(
            self.check.check_format("%{foo} string", "%{bar} string", False, None)
        )
        self.assertTrue(
            self.check.check_format("{foo} string", "{bar} string", False, None)
        )


class AutomatticComponentsCheckTest(CheckTestCase):
    check = AutomatticComponentsCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_highlight = (
            "automattic-components-format",
            "{{ strong }} hello, world {{/strong}}, {{ languages /}}",
            [
                (0, 12, "{{ strong }}"),
                (26, 37, "{{/strong}}"),
                (39, 55, "{{ languages /}}"),
            ],
        )

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "{{foo}} string {{/foo}}", "{{foo}} string {{/foo}}", False, None
            )
        )
        self.assertFalse(
            self.check.check_format("{{foo/}} string", "{{foo/}} string", False, None)
        )

    def test_missing_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{{foo}} string", "string", False, None)
        )
        self.assertTrue(
            self.check.check_format(
                "{{foo}} string {{/foo}}", "{{foo}} string", False, None
            )
        )

    def test_wrong_format(self) -> None:
        self.assertTrue(
            self.check.check_format(
                "{{foo}} string {{/foo}}", "{{foo}} string {{/bar}}", False, None
            )
        )
        self.assertTrue(
            self.check.check_format("{{foo/}} string", "{{baz/}} string", False, None)
        )


class MultipleUnnamedFormatsCheckTestCase(SimpleTestCase):
    check = MultipleUnnamedFormatsCheck()

    def test_none_flag(self) -> None:
        self.assertFalse(self.check.check_source(["text"], MockUnit()))

    def test_none_format(self) -> None:
        self.assertFalse(self.check.check_source(["text"], MockUnit(flags="c-format")))

    def test_good(self) -> None:
        self.assertFalse(
            self.check.check_source(["%1$s %2$s"], MockUnit(flags="c-format"))
        )

    def test_bad_c(self) -> None:
        self.assertTrue(self.check.check_source(["%s %s"], MockUnit(flags="c-format")))

    def test_bad_python(self) -> None:
        self.assertTrue(
            self.check.check_source(["{} {}"], MockUnit(flags="python-brace-format"))
        )

    def test_good_multi_format(self) -> None:
        self.assertFalse(
            self.check.check_source(
                ["Test %s"], MockUnit(flags="c-format,python-format")
            )
        )

    def test_good_brace_format(self) -> None:
        self.assertFalse(
            self.check.check_source(
                ["Recognition {progress}% ({current_job}/{total_jobs})"],
                MockUnit(flags="python-brace-format"),
            )
        )

    def test_bad_brace_format(self) -> None:
        self.assertTrue(
            self.check.check_source(
                ["Recognition {}% ({}/{})"], MockUnit(flags="python-brace-format")
            )
        )
