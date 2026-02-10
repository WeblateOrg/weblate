# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for merge duplicates functionality across formats.

Verifies merging logic, context stripping, and location aggregation
for Markdown, HTML, and Plain Text.
"""

import io
import uuid

from django.test import TestCase

from weblate.formats.convert import HTMLFormat, MarkdownFormat, PlainTextFormat
from weblate.trans.tests.test_models import RepoTestCase


class TestFormatsMerge(TestCase):
    """Unit tests: Verify parser logic handles merging correctly in memory."""

    def _load_format(
        self,
        content: bytes,
        format_class: type,
        extension: str,
        params: dict | None = None,
    ):
        """
        Load a format with explicit stream positioning.

        Args:
            content: The bytes content of the file.
            format_class: The class of the parser (e.g., MarkdownFormat).
            extension: File extension string (e.g., 'md').
            params: Dictionary of file_format_params. If None, passes None to parser.

        """
        f = io.BytesIO(content)
        f.name = f"test.{extension}"
        f.mode = "rb"  # type: ignore[misc]

        # Reset stream before instantiation to allow header detection
        f.seek(0)
        # Pass params exactly as received to test None vs {} behavior
        fmt = format_class(f, file_format_params=params)

        # Reset again before loading to ensure full read
        f.seek(0)
        return fmt.load(f, None)

    def test_markdown_merge_and_location(self):
        """Verify Markdown merging deduplicates items and aggregates locations."""
        content = b"- Item\n- Item\n- Item\n"
        # Test merging ENABLED
        store = self._load_format(
            content, MarkdownFormat, "md", {"markdown_merge_duplicates": True}
        )
        units = [u for u in store.units if u.source.strip() == "Item"]

        self.assertEqual(len(units), 1, "Should have 1 unit when merged")

        # Verify all 3 locations were aggregated into the single unit
        self.assertEqual(len(list(units[0].getlocations())), 3)

        # Robust check: Assert context is "falsy" (None, "", or [])
        self.assertFalse(units[0].getcontext())

    def test_markdown_explicit_false(self):
        """Verify that explicitly setting False disables merging."""
        content = b"- Item\n- Item"
        # Test merging explicitly DISABLED
        store = self._load_format(
            content, MarkdownFormat, "md", {"markdown_merge_duplicates": False}
        )
        units = [u for u in store.units if u.source.strip() == "Item"]

        self.assertEqual(len(units), 2, "Should have 2 units when explicitly disabled")

        # Verify locations are distinct (not merged/aggregated)
        loc_0 = list(units[0].getlocations())
        loc_1 = list(units[1].getlocations())

        self.assertEqual(len(loc_0), 1, "First unit should have exactly 1 location")
        self.assertEqual(len(loc_1), 1, "Second unit should have exactly 1 location")
        self.assertNotEqual(
            loc_0, loc_1, "Locations should be distinct (different lines)"
        )

    def test_markdown_default_behavior_empty_dict(self):
        """
        Verify behavior when params is an empty dict.

        Assumption: Default is FALSE (do not merge).
        """
        content = b"- Item\n- Item"
        store = self._load_format(content, MarkdownFormat, "md", {})
        units = [u for u in store.units if u.source.strip() == "Item"]

        self.assertEqual(len(units), 2, "Empty dict param should default to NO merge")

    def test_markdown_default_behavior_none(self):
        """
        Verify behavior when params is None (argument missing).

        This protects against regressions where 'if params:' might fail for None.
        """
        content = b"- Item\n- Item"
        store = self._load_format(content, MarkdownFormat, "md", None)
        units = [u for u in store.units if u.source.strip() == "Item"]

        self.assertEqual(len(units), 2, "None param should default to NO merge")

    def test_markdown_table_rows(self):
        """Verify identical strings in Markdown tables are merged."""
        content = b"| Header |\n|---|\n| Cell |\n| Cell |\n"
        store = self._load_format(
            content, MarkdownFormat, "md", {"markdown_merge_duplicates": True}
        )
        units = [u for u in store.units if u.source.strip() == "Cell"]
        self.assertEqual(len(units), 1)
        self.assertFalse(units[0].getcontext())

    def test_markdown_mixed_content_safety(self):
        """Ensure distinct strings in a table are NOT merged (sanity check)."""
        content = b"| Col |\n|---|\n| Yes |\n| No |\n| Yes |\n"
        store = self._load_format(
            content, MarkdownFormat, "md", {"markdown_merge_duplicates": True}
        )
        yes_units = [u for u in store.units if u.source.strip() == "Yes"]
        no_units = [u for u in store.units if u.source.strip() == "No"]

        self.assertEqual(len(yes_units), 1)
        self.assertEqual(len(no_units), 1)

    def test_html_merge(self):
        """Verify HTML merging works when enabled."""
        content = b"<html><body><p>Hello</p><div>Hello</div></body></html>"
        store = self._load_format(
            content, HTMLFormat, "html", {"html_merge_duplicates": True}
        )
        units = [u for u in store.units if u.source.strip() == "Hello"]
        self.assertEqual(len(units), 1)

    def test_txt_merge(self):
        """Verify Plain Text merging works when enabled."""
        content = b"Line A\n\nLine B\n\nLine A\n"
        store = self._load_format(
            content, PlainTextFormat, "txt", {"txt_merge_duplicates": True}
        )
        # Strip is important here as PlainText parser might keep newlines
        line_a_units = [u for u in store.units if u.source.strip() == "Line A"]
        self.assertEqual(len(line_a_units), 1)


class TestMergeIntegration(RepoTestCase):
    """
    Integration tests: Verify DB configuration correctly propagates to the parser.

    Uses Markdown as the representative format for integration logic.
    """

    def _create_integration_env(self, params: dict | None = None):
        """Create a Component in the DB with specific file format params."""
        unique_slug = f"merge-md-{uuid.uuid4().hex[:6]}"

        component = self._create_component(
            "markdown",
            "*.md",
            slug=unique_slug,
            name="Test Markdown Merge",
            file_format_params=params or {},
        )
        component.create_translations_immediate()
        return component.translation_set.get(language_code="en")

    def _load_store_from_db(self, translation, content):
        """Simulate Weblate loading the file using the DB configuration."""
        f = io.BytesIO(content)
        f.name = translation.filename
        # Ensure params come from the Component DB model
        params = translation.component.file_format_params

        f.seek(0)
        fmt = MarkdownFormat(f, file_format_params=params)
        f.seek(0)
        return fmt.load(f, None)

    def test_db_config_enabled(self):
        """Verify that setting the option to True in DB enables merging."""
        translation = self._create_integration_env({"markdown_merge_duplicates": True})
        content = b"- A\n- A"
        store = self._load_store_from_db(translation, content)

        units = [u for u in store.units if u.source.strip() == "A"]
        self.assertEqual(len(units), 1)

    def test_db_config_disabled(self):
        """Verify that setting the option to False in DB disables merging."""
        translation = self._create_integration_env({"markdown_merge_duplicates": False})
        content = b"- A\n- A"
        store = self._load_store_from_db(translation, content)

        units = [u for u in store.units if u.source.strip() == "A"]
        self.assertEqual(len(units), 2)
