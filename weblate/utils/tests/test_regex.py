# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from unittest.mock import patch

from django.test import SimpleTestCase

from weblate.utils.regex import builtin_regex_finditer


class BuiltinRegexTest(SimpleTestCase):
    def test_groups_spans_and_flags(self) -> None:
        for pattern, text, flags in (
            (r"(?P<name>[a-z]+)=(\d+)", "A=12 b=34", re.IGNORECASE),
            (r"^(.+)$", "first\nsecond", re.MULTILINE),
            (r"a(.)b", "a\nb", re.DOTALL),
            (r"a \s+ b # comment", "a  b", re.VERBOSE),
            (r"\w+", "é ascii", re.ASCII),
            (r"[a-z]+", "İſK", re.IGNORECASE),
        ):
            with self.subTest(pattern=pattern, flags=flags):
                compiled = re.compile(pattern, flags)
                expected = [
                    (match.span(), match.groups(), match.groupdict())
                    for match in compiled.finditer(text)
                ]
                self.assertEqual(
                    [
                        (match.span(), match.groups(), match.groupdict())
                        for match in builtin_regex_finditer(compiled, text)
                    ],
                    expected,
                )

    def test_timeout_is_enforced_during_iteration(self) -> None:
        with (
            patch("weblate.utils.regex.REGEX_TIMEOUT", 0),
            self.assertRaises(TimeoutError),
        ):
            list(builtin_regex_finditer(re.compile(r"\w+"), "value"))
