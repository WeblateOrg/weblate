# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for various helper utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.test import SimpleTestCase

from weblate.auth.utils import TeamNameAllocator, format_address

if TYPE_CHECKING:
    from collections.abc import Iterable


class CountingNames(set[str]):
    def __init__(self, names: Iterable[str]) -> None:
        super().__init__(names)
        self.probes = 0

    def __contains__(self, name: object) -> bool:
        self.probes += 1
        return super().__contains__(name)


class TeamNameAllocatorTest(SimpleTestCase):
    def test_reserved_suffixes(self) -> None:
        allocator = TeamNameAllocator(["Legacy", "Legacy (2)", "Legacy (4)"], 150)
        self.assertEqual(allocator.allocate("Legacy"), "Legacy (3)")
        self.assertEqual(allocator.allocate("Legacy"), "Legacy (5)")

    def test_many_duplicates_have_linear_candidate_checks(self) -> None:
        allocator = TeamNameAllocator(["Legacy"], 150)
        names_to_check = CountingNames(allocator.reserved_names)
        allocator.reserved_names = names_to_check
        names = [allocator.allocate("Legacy") for _ in range(10000)]
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(names[-1], "Legacy (10001)")
        self.assertLessEqual(names_to_check.probes, 10000)

    def test_truncated_prefixes_share_suffix_counters(self) -> None:
        originals = [f"{'x' * 146}{index:04}" for index in range(1000)]
        allocator = TeamNameAllocator(originals, 150)
        names_to_check = CountingNames(allocator.reserved_names)
        allocator.reserved_names = names_to_check
        names = [allocator.allocate(name) for name in originals]
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(all(len(name) <= 150 for name in names))
        self.assertLessEqual(names_to_check.probes, 1000)


class FormatAddressTestCase(SimpleTestCase):
    def test_unicode(self) -> None:
        self.assertEqual(
            format_address("Michal Čihař", "michal@weblate.org"),
            "Michal Čihař <michal@weblate.org>",
        )

    def test_invalid(self) -> None:
        self.assertEqual(
            format_address("<a>", "noreply@example.com"), "a <noreply@example.com>"
        )

    def test_value_error(self) -> None:
        with self.assertRaises(ValueError):
            format_address("x", ".@example.com")
