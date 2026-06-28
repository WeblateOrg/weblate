# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helper for quality checks tests."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from unittest import SkipTest

from django.test import SimpleTestCase

from weblate.checks.base import Highlight
from weblate.checks.format import BaseFormatCheck
from weblate.trans.tests.factories import make_unit

if TYPE_CHECKING:
    from weblate.checks.base import BaseCheck

CheckData = tuple[str, str, str]
CheckInputData = tuple[str | list[str], str, str]


class CheckTestCase(SimpleTestCase, ABC):
    """Generic test, also serves for testing base class."""

    default_lang = "cs"

    def setUp(self) -> None:
        self.test_empty: CheckData = ("", "", "")
        self.test_good_matching: CheckData = ("string", "string", "")
        self.test_good_none: CheckData = ("string", "string", "")
        self.test_good_ignore: CheckData | None = None
        self.test_good_flag: CheckData | None = None
        self.test_failure_1: CheckData | None = None
        self.test_failure_2: CheckData | None = None
        self.test_failure_3: CheckData | None = None
        self.test_ignore_check: CheckData = (
            "x",
            "x",
            self.check.ignore_string if self.check else "",
        )
        self.test_highlight: tuple[str, str, list[tuple[int, int, str]]] | None = None

    @property
    @abstractmethod
    def check(self) -> BaseCheck:
        raise NotImplementedError

    def do_test(
        self, expected: bool, data: CheckInputData | None, lang: str | None = None
    ):
        """Perform single check if we have data to test."""
        if data is None:
            msg = "Test data not provided"
            raise SkipTest(msg)
        if isinstance(self.check, BaseFormatCheck):
            # Skip for format tests
            msg = "Test not supported"
            raise SkipTest(msg)
        if lang is None:
            lang = self.default_lang
        params = f'"{data[0]}"/"{data[1]}" ({data[2]})'

        unit = make_unit(None, data[2], lang, source=data[0])

        # Verify skip logic
        should_skip = self.check.should_skip(unit)
        if expected:
            self.assertFalse(should_skip, msg=f"Check should not skip for {params}")
        elif should_skip:
            # There is nothing to test here
            return None

        # Verify check logic
        result = self.check.check_single(
            data[0][0] if isinstance(data[0], list) else data[0], data[1], unit
        )
        if expected:
            self.assertTrue(result, msg=f"Check did not fire for {params}")
        else:
            self.assertFalse(result, msg=f"Check did fire for {params}")
        return result

    def test_single_good_matching(self) -> None:
        self.do_test(False, self.test_good_matching)

    def test_single_good_none(self) -> None:
        self.do_test(False, self.test_good_none)

    def test_single_good_ignore(self) -> None:
        self.do_test(False, self.test_good_ignore)

    def test_single_empty(self) -> None:
        self.do_test(False, self.test_empty)

    def test_single_failure_1(self) -> None:
        self.do_test(True, self.test_failure_1)

    def test_single_failure_2(self) -> None:
        self.do_test(True, self.test_failure_2)

    def test_single_failure_3(self) -> None:
        self.do_test(True, self.test_failure_3)

    def test_check_good_flag(self) -> None:
        if self.test_good_flag is None:
            msg = "Test data not provided"
            raise SkipTest(msg)
        self.assertFalse(
            self.check.check_target(
                [self.test_good_flag[0]],
                [self.test_good_flag[1]],
                make_unit(
                    None,
                    self.test_good_flag[2],
                    self.default_lang,
                    source=self.test_good_flag[0],
                ),
            )
        )

    def test_check_good_matching_singular(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching[0]],
                [self.test_good_matching[1]],
                make_unit(
                    None,
                    self.test_good_matching[2],
                    self.default_lang,
                    source=self.test_good_matching[0],
                ),
            )
        )

    def test_check_good_none_singular(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_good_none[0]],
                [self.test_good_none[1]],
                make_unit(
                    None,
                    self.test_good_none[2],
                    self.default_lang,
                    source=self.test_good_none[0],
                ),
            )
        )

    def test_check_good_ignore_singular(self) -> None:
        if self.test_good_ignore is None:
            msg = "Test data not provided"
            raise SkipTest(msg)
        self.assertFalse(
            self.check.check_target(
                [self.test_good_ignore[0]],
                [self.test_good_ignore[1]],
                make_unit(
                    None,
                    self.test_good_ignore[2],
                    self.default_lang,
                    source=self.test_good_ignore[0],
                ),
            )
        )

    def test_check_good_matching_plural(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching[0]] * 2,
                [self.test_good_matching[1]] * 3,
                make_unit(
                    None,
                    self.test_good_matching[2],
                    self.default_lang,
                    source=self.test_good_matching[0],
                ),
            )
        )

    def test_check_failure_1_singular(self) -> None:
        if self.test_failure_1 is None:
            msg = "Test data not provided"
            raise SkipTest(msg)
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_1[0]],
                [self.test_failure_1[1]],
                make_unit(
                    None,
                    self.test_failure_1[2],
                    self.default_lang,
                    source=self.test_failure_1[0],
                ),
            )
        )

    def test_check_failure_1_plural(self) -> None:
        if self.test_failure_1 is None:
            msg = "Test data not provided"
            raise SkipTest(msg)
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_1[0]] * 2,
                [self.test_failure_1[1]] * 3,
                make_unit(
                    None,
                    self.test_failure_1[2],
                    self.default_lang,
                    source=self.test_failure_1[0],
                ),
            )
        )

    def test_check_failure_2_singular(self) -> None:
        if self.test_failure_2 is None:
            msg = "Test data not provided"
            raise SkipTest(msg)
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_2[0]],
                [self.test_failure_2[1]],
                make_unit(
                    None,
                    self.test_failure_2[2],
                    self.default_lang,
                    source=self.test_failure_2[0],
                ),
            )
        )

    def test_check_failure_3_singular(self) -> None:
        if self.test_failure_3 is None:
            msg = "Test data not provided"
            raise SkipTest(msg)
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_3[0]],
                [self.test_failure_3[1]],
                make_unit(
                    None,
                    self.test_failure_3[2],
                    self.default_lang,
                    source=self.test_failure_3[0],
                ),
            )
        )

    def test_check_ignore_check(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_ignore_check[0]] * 2,
                [self.test_ignore_check[1]] * 3,
                make_unit(
                    None,
                    self.test_ignore_check[2],
                    self.default_lang,
                    source=self.test_ignore_check[0],
                ),
            )
        )

    def test_check_highlight(self) -> None:
        if self.test_highlight is None:
            msg = "Test data not provided"
            raise SkipTest(msg)
        unit = make_unit(
            None,
            self.test_highlight[0],
            self.default_lang,
            source=self.test_highlight[1],
        )
        highlights = list(self.check.check_highlight(self.test_highlight[1], unit))
        self.assertTrue(
            all(isinstance(highlight, Highlight) for highlight in highlights)
        )
        self.assertEqual(
            [
                (highlight.start, highlight.end, highlight.text)
                for highlight in highlights
            ],
            self.test_highlight[2],
        )
