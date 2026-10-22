# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © Philipp Wolfer <ph.wolfer@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for AngularJS checks."""

from __future__ import annotations

from time import monotonic

from weblate.checks.angularjs import AngularJSInterpolationCheck
from weblate.checks.tests.test_checks import CheckTestCase
from weblate.trans.tests.factories import make_unit


class AngularJSInterpolationCheckTest(CheckTestCase):
    check = AngularJSInterpolationCheck()

    def test_no_format(self) -> None:
        self.assertFalse(
            self.check.check_format("strins", "string", False, make_unit())
        )

    def test_format(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "{{name}} string {{other}}",
                "{{name}} {{other}} string",
                False,
                make_unit(),
            )
        )

    def test_format_ignore_position(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "{{name}} string {{other}}",
                "{{other}} string {{name}}",
                False,
                make_unit(),
            )
        )

    def test_different_whitespace(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "{{ name   }} string", "{{name}} string", False, make_unit()
            )
        )

    def test_missing_format(self) -> None:
        self.assertTrue(
            self.check.check_format("{{name}} string", "string", False, make_unit())
        )

    def test_wrong_value(self) -> None:
        self.assertTrue(
            self.check.check_format(
                "{{name}} string", "{{nameerror}} string", False, make_unit()
            )
        )

    def test_extended_formatting(self) -> None:
        self.assertFalse(
            self.check.check_format(
                "Value: {{ something.value | currency }}",
                "Wert: {{ something.value | currency }}",
                False,
                make_unit(),
            )
        )
        self.assertTrue(
            self.check.check_format(
                "Value: {{ something.value | currency }}",
                "Value: {{ something.value }}",
                False,
                make_unit(),
            )
        )

    def test_unterminated_interpolations(self) -> None:
        target = "{{" * 32000
        started = monotonic()
        self.assertEqual(self.check.extract_matches(target), [])
        self.assertLess(monotonic() - started, 1)

    def test_nested_opening_marker(self) -> None:
        self.assertEqual(
            self.check.extract_matches("{{broken {{ valid }}"), ["broken{{valid"]
        )

    def test_quoted_opening_marker(self) -> None:
        source = '{{ value === "{{" ? foo : bar }}'
        target = '{{ other === "{{" ? foo : bar }}'
        self.assertEqual(self.check.extract_matches(source), ['value==="{{"?foo:bar'])
        self.assertTrue(self.check.check_format(source, target, False, make_unit()))

        highlights = list(
            self.check.check_highlight(
                source, make_unit("angularjs_format", flags="angularjs-format")
            )
        )
        self.assertEqual(
            [(0, len(source), source)],
            [
                (highlight.start, highlight.end, highlight.text)
                for highlight in highlights
            ],
        )

    def test_unterminated_suffix_after_valid_interpolation(self) -> None:
        target = "{{ valid }}" + "{{" * 32000
        started = monotonic()
        self.assertEqual(self.check.extract_matches(target), ["valid"])
        self.assertLess(monotonic() - started, 1)

    def test_braces_inside_expression(self) -> None:
        self.assertEqual(
            self.check.extract_matches("{{ {name: value} }}"), ["{name:value}"]
        )

    def test_check_highlight(self) -> None:
        highlights = list(
            self.check.check_highlight(
                "{{name}} {{ something.value | currency }} string",
                make_unit("angularjs_format", flags="angularjs-format"),
            )
        )
        self.assertEqual(
            [(0, 8, "{{name}}"), (9, 41, "{{ something.value | currency }}")],
            [
                (highlight.start, highlight.end, highlight.text)
                for highlight in highlights
            ],
        )

    def test_check_highlight_ignored(self) -> None:
        highlights = list(
            self.check.check_highlight(
                "{{name}} {{other}} string",
                make_unit("angularjs_format", flags="ignore-angularjs-format"),
            )
        )
        self.assertEqual([], highlights)
