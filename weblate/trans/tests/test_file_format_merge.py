# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for merge duplicates functionality across formats.

Verifies merging logic, context stripping, and location aggregation
for Markdown, HTML, and Plain Text.
"""

import io
from typing import ClassVar

from django.test import TestCase

from weblate.formats.convert import HTMLFormat, MarkdownFormat, PlainTextFormat


class TestFormatsMerge(TestCase):
    # Mapping classes to their standard extensions to avoid parser warnings
    # from translate-toolkit regarding file types.
    EXTENSIONS: ClassVar[dict] = {
        MarkdownFormat: "md",
        HTMLFormat: "html",
        PlainTextFormat: "txt",
    }

    def _load_format(
        self,
        content: bytes,
        format_class,
        param_name: str,
        merge_duplicates: bool,
    ):
        """Generic helper to load a format with specific merge parameters."""
        f = io.BytesIO(content)
        # Dynamically set the correct extension (e.g., test.md, test.html)
        ext = self.EXTENSIONS.get(format_class, "txt")
        f.name = f"test.{ext}"
        f.mode = "rb"  # type: ignore[misc]
        f.seek(0)

        params = {param_name: True} if merge_duplicates else {}
        fmt = format_class(f, file_format_params=params)

        f.seek(0)
        return fmt.load(f, None)

    def test_markdown_merge_and_location(self):
        """Verify Markdown merging deduplicates items and aggregates locations."""
        content = b"- Item\n- Item\n- Item\n"

        # 1. Default: Should keep separate units
        store_def = self._load_format(
            content, MarkdownFormat, "markdown_merge_duplicates", False
        )
        items_def = [u for u in store_def.units if u.source == "Item"]
        self.assertEqual(len(items_def), 3)

        # 2. Merged: Should contain a single unit
        store_merged = self._load_format(
            content, MarkdownFormat, "markdown_merge_duplicates", True
        )
        items_merged = [u for u in store_merged.units if u.source == "Item"]
        self.assertEqual(len(items_merged), 1)

        # Verify location accumulation (all line numbers preserved)
        self.assertEqual(len(list(items_merged[0].getlocations())), 3)

    def test_markdown_table_rows(self):
        """Verify identical strings in Markdown tables are merged."""
        # This covers the original issue report regarding tables
        content = b"| Header |\n|---|\n| Cell |\n| Cell |\n"

        store = self._load_format(
            content, MarkdownFormat, "markdown_merge_duplicates", True
        )
        units = [u for u in store.units if u.source == "Cell"]

        self.assertEqual(len(units), 1)
        # Ensure context is stripped (no line numbers affecting ID)
        self.assertFalse(units[0].getcontext())

    def test_markdown_mixed_content_safety(self):
        """Ensure distinct strings in a table are NOT merged."""
        content = (
            b"| Col A | Col B |\n|---|---|\n| A | Yes |\n| B | No |\n| C | Yes |\n"
        )
        store = self._load_format(
            content, MarkdownFormat, "markdown_merge_duplicates", True
        )

        yes_units = [u for u in store.units if u.source == "Yes"]
        no_units = [u for u in store.units if u.source == "No"]

        self.assertEqual(len(yes_units), 1)
        self.assertEqual(len(no_units), 1)

    def test_html_merge(self):
        """Verify HTML merging works when enabled."""
        content = b"<html><body><p>Hello</p><div>Hello</div></body></html>"

        # 1. Default (False): Should have 2 separate "Hello" units
        store_def = self._load_format(
            content, HTMLFormat, "html_merge_duplicates", False
        )
        hello_units_def = [u for u in store_def.units if u.source == "Hello"]
        self.assertEqual(len(hello_units_def), 2)

        # 2. Merged (True): Should have 1 "Hello" unit
        store_merged = self._load_format(
            content, HTMLFormat, "html_merge_duplicates", True
        )
        hello_units_merged = [u for u in store_merged.units if u.source == "Hello"]
        self.assertEqual(len(hello_units_merged), 1)

    def test_txt_merge(self):
        """Verify Plain Text merging works when enabled."""
        content = b"Line A\n\nLine B\n\nLine A\n"

        # 1. Default (False): Should see duplicates
        store_def = self._load_format(
            content, PlainTextFormat, "txt_merge_duplicates", False
        )
        # Filter with strip() to avoid parser newline noise
        line_a_def = [u for u in store_def.units if u.source.strip() == "Line A"]
        self.assertEqual(len(line_a_def), 2, "Default: Should keep separate units")

        # 2. Merged (True): Should deduplicate
        store_merged = self._load_format(
            content, PlainTextFormat, "txt_merge_duplicates", True
        )

        line_a_merged = [u for u in store_merged.units if u.source.strip() == "Line A"]

        self.assertEqual(
            len(line_a_merged), 1, "Merged: Should consolidate identical strings"
        )

        # Verify context is stripped to allow the merge
        self.assertFalse(line_a_merged[0].getcontext())
