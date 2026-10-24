# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for generated reStructuredText tables."""

from __future__ import annotations

from unittest import TestCase

from docutils import nodes
from docutils.core import publish_doctree

from weblate.utils.rst import FullWidthRow, format_table


class TableTest(TestCase):
    def test_group_rows_span_columns(self) -> None:
        text = "".join(
            format_table(
                [
                    FullWidthRow(
                        "**First group**\n\nA description with several words."
                    ),
                    ["field", "Label", "Help text"],
                    FullWidthRow("**Middle group**"),
                    ["other", "Label", "More help"],
                    FullWidthRow("**Last group**"),
                ],
                ["Name", "Label", "Description"],
            )
        )
        document = publish_doctree(text, settings_overrides={"halt_level": 2})
        rows = list(document.findall(nodes.row))
        self.assertEqual(len(rows), 6)
        for index in (1, 3, 5):
            self.assertEqual(len(rows[index]), 1)
            entry = rows[index][0]
            assert isinstance(entry, nodes.entry)
            self.assertEqual(entry["morecols"], 2)
        self.assertEqual(len(list(document.findall(nodes.strong))), 3)
        self.assertEqual(len(list(rows[1][0].findall(nodes.paragraph))), 2)

    def test_description_wraps_without_widening_columns(self) -> None:
        normal = [["field", "Label", "Help text"]]
        plain = format_table(normal, None)
        grouped = format_table(
            [
                FullWidthRow("**Group**\n\n" + "Several words of description. " * 20),
                *normal,
            ],
            None,
        )
        self.assertEqual(max(map(len, plain)), max(map(len, grouped)))
        publish_doctree("".join(grouped), settings_overrides={"halt_level": 2})

    def test_long_word_expands_merged_row(self) -> None:
        word = "LongGroupTitleWithoutSpaces"
        text = "".join(format_table([FullWidthRow(word), ["a", "b", "c"]], None))
        document = publish_doctree(text, settings_overrides={"halt_level": 2})
        self.assertIn(word, document.astext())
        self.assertEqual(len({len(line) for line in text.splitlines()}), 1)

    def test_nested_rows_with_groups(self) -> None:
        text = "".join(
            format_table(
                [
                    FullWidthRow("**Group**"),
                    ["shared", [["first", "one"], ["second", "two"]]],
                    FullWidthRow("**Next group**"),
                    ["last", "field", "help\ntext"],
                ],
                None,
            )
        )
        document = publish_doctree(text, settings_overrides={"halt_level": 2})
        entries = list(document.findall(nodes.entry))
        shared = next(entry for entry in entries if entry.astext() == "shared")
        self.assertEqual(shared["morerows"], 1)
        self.assertEqual(sum(entry.get("morecols", 0) == 2 for entry in entries), 2)

    def test_plain_table_output(self) -> None:
        self.assertEqual(
            "".join(format_table([["a", "b"], ["c", "d"]], None)),
            "+---+---+\n| a | b |\n+---+---+\n| c | d |\n+---+---+\n",
        )
