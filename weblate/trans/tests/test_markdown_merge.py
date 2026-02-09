# Copyright © Michal Čihař <michal@weblate.org>

# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for Markdown merge duplicates functionality.

Verifies merging logic, context stripping, location aggregation, and Unicode support.
"""

import io

from django.test import TestCase

from weblate.formats.convert import MarkdownFormat


class TestMarkdownMerge(TestCase):
    def _load_markdown(self, content: bytes, merge_duplicates: bool):
        """Load a Markdown file with specific parameters."""
        f = io.BytesIO(content)
        f.name = "test.md"
        # Keep f.mode as some parsers might check for it
        f.mode = "rb"
        f.seek(0)

        params = {"markdown_merge_duplicates": True} if merge_duplicates else {}
        fmt = MarkdownFormat(f, file_format_params=params)

        f.seek(0)

        return fmt.load(f, None)

    def test_merge_and_location_accumulation(self):
        """Verify that merging deduplicates items and aggregates their locations."""
        content = b"- Item\n- Item\n- Item\n"

        # 1. Default behavior: Should keep units separate
        store_def = self._load_markdown(content, merge_duplicates=False)
        items_def = [u for u in store_def.units if u.source == "Item"]
        self.assertEqual(len(items_def), 3, "Default: Should keep 3 items separate.")

        # 2. Merged behavior: Should deduplicate into exactly 1 unit
        store_merged = self._load_markdown(content, merge_duplicates=True)
        items_merged = [u for u in store_merged.units if u.source == "Item"]
        self.assertEqual(
            len(items_merged), 1, "Merged: Should deduplicate into 1 unit."
        )

        # 3. Verify Location Aggregation
        unit = items_merged[0]
        # Robust retrieval of locations
        get_locs = getattr(unit, "getlocations", list)
        locs = list(get_locs())

        self.assertEqual(
            len(locs),
            3,
            f"Should accumulate all 3 locations. Found: {locs}",
        )
        self.assertTrue(all(loc for loc in locs), "Locations should not be empty.")

    def test_context_is_disabled_when_merging(self):
        """
        Verify that line-based context is stripped when merging.

        This ensures the unit is not tied to a specific line number.
        """
        content = b"- Item A\n- Item A\n"

        # Case A: Without merging, units usually have specific contexts
        store_no_merge = self._load_markdown(content, merge_duplicates=False)
        units_no_merge = [u for u in store_no_merge.units if u.source == "Item A"]
        self.assertTrue(units_no_merge)
        self.assertTrue(
            any(u.getcontext() for u in units_no_merge),
            "Default: At least one unit should have context.",
        )

        # Case B: With merging, context should be empty to allow deduplication
        store_merge = self._load_markdown(content, merge_duplicates=True)
        units_merge = [u for u in store_merge.units if u.source == "Item A"]
        self.assertEqual(len(units_merge), 1)
        self.assertFalse(
            units_merge[0].getcontext(),
            "Merged: Unit should NOT have a specific line context.",
        )

    def test_unicode_merging(self):
        """Verify merging works correctly with non-ASCII characters."""
        content = b"- \xc3\x81pple\n- \xc3\x81pple\n"

        store = self._load_markdown(content, merge_duplicates=True)
        units = [u for u in store.units if u.source == "Ápple"]

        self.assertEqual(len(units), 1, "Should correctly merge Unicode strings.")
        self.assertEqual(units[0].source, "Ápple")

    def test_merge_table_rows(self):
        """Verify identical strings in tables are merged."""
        content = b"| Header |\n|---|\n| Cell |\n| Cell |\n"

        store = self._load_markdown(content, merge_duplicates=True)
        units = [u for u in store.units if u.source == "Cell"]

        self.assertEqual(len(units), 1, "Should merge identical table rows.")

    def test_distinction_by_case_and_punctuation(self):
        """Verify units are NOT merged if content differs slightly."""
        content = b"- Yes\n- yes\n- Yes.\n"
        store = self._load_markdown(content, merge_duplicates=True)

        self.assertEqual(len([u for u in store.units if u.source == "Yes"]), 1)
        self.assertEqual(len([u for u in store.units if u.source == "yes"]), 1)
        self.assertEqual(len([u for u in store.units if u.source == "Yes."]), 1)

        # Filter out empty units (like trailing newlines) before counting total
        real_units = [u for u in store.units if u.source and u.source.strip()]
        self.assertEqual(len(real_units), 3, "Should have exactly 3 real units")

    def test_mixed_content_safety(self):
        """Ensure distinct strings in a table are not merged."""
        content = (
            b"| Col A | Col B |\n|---|---|\n| A | Yes |\n| B | No |\n| C | Yes |\n"
        )

        store = self._load_markdown(content, merge_duplicates=True)

        yes_units = [u for u in store.units if u.source == "Yes"]
        no_units = [u for u in store.units if u.source == "No"]

        self.assertEqual(len(yes_units), 1, "Should merge duplicate 'Yes'")
        self.assertEqual(len(no_units), 1, "Should keep 'No'")
        self.assertNotEqual(yes_units[0].source, no_units[0].source)
