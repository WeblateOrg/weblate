# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Philipp Wolfer <ph.wolfer@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for AngularJS checks."""

from weblate.checks.angularjs import AngularJSInterpolationCheck
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit


class AngularJSInterpolationCheckTest(CheckTestCase):
    check = AngularJSInterpolationCheck()

    def test_no_format(self) -> None:
        self.assertFalse(self.check.check_format("strins", "string", False, None))

    def test_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "{{name}} string {{other}}", "{{name}} {{other}} string", False, None
            )
        )

    def test_format_ignore_position(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "{{name}} string {{other}}", "{{other}} string {{name}}", False, None
            )
        )

    def test_different_whitespace(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "{{ name   }} string", "{{name}} string", False, None
            )
        )

    def test_missing_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{{name}} string", "string", False, None)
        )

    def test_wrong_value(self) -> None:
        self.assertTrue(
            self.check.check_format(
                "{{name}} string", "{{nameerror}} string", False, None
            )
        )

    def test_extended_formatting(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "Value: {{ something.value | currency }}",
                "Wert: {{ something.value | currency }}",
                False,
                None,
            )
        )
        self.assertTrue(
            self.check.check_format(
                "Value: {{ something.value | currency }}",
                "Value: {{ something.value }}",
                False,
                None,
            )
        )

    def test_check_highlight(self) -> None:
        highlights = list(
            self.check.check_highlight(
                "{{name}} {{ something.value | currency }} string",
                MockUnit("angularjs_format", flags="angularjs-format"),
            )
        )
        self.assertEqual(
            [(0, 8, "{{name}}"), (9, 41, "{{ something.value | currency }}")],
            highlights,
        )

    def test_check_highlight_ignored(self) -> None:
        highlights = list(
            self.check.check_highlight(
                "{{name}} {{other}} string",
                MockUnit("angularjs_format", flags="ignore-angularjs-format"),
            )
        )
        self.assertEqual([], highlights)
