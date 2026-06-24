# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase

from weblate.checks.utils import highlight_string, replace_highlighted
from weblate.trans.tests.factories import make_unit, set_unit_flags

REPLACEMENT_CALLS: list[int] = []


def marker_replacement(start: int) -> str:
    REPLACEMENT_CALLS.append(start)
    return f"marker-{start}"


class HighlightTestCase(SimpleTestCase):
    def test_simple(self) -> None:
        unit = make_unit(
            source="simple {format} string",
            flags="python-brace-format",
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 15, "{format}")],
        )

    def test_multi(self) -> None:
        unit = make_unit(
            source="simple {format} %d string",
            flags="python-brace-format, python-format",
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 15, "{format}"), (16, 18, "%d")],
        )

    def test_overlap(self) -> None:
        unit = make_unit(
            source='nested <a href="{format}">string</a>',
            flags="python-brace-format",
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 26, '<a href="{format}">'), (32, 36, "</a>")],
        )

    def test_overlap_non_nested(self) -> None:
        # The 2 flags match partially overlapping spans
        # 'python-brace-format' matches {user.name}.
        # "placeholders:r"\$\{\w+" matches ${user.
        unit = make_unit(
            source="nested ${user.name} non-overlapping",
            flags=r'python-brace-format, placeholders:r"\$\{\w+"',
        )
        self.assertEqual(
            highlight_string(unit.source, unit),
            [(7, 19, "${user.name}")],
        )

    def test_syntax(self) -> None:
        unit = make_unit(
            source="Text with a `link <https://www.sphinx-doc.org>`_.",
            flags="rst-text",
        )
        self.assertEqual(
            highlight_string(unit.source, unit, highlight_syntax=True),
            [(12, 13, "`"), (18, 46, "<https://www.sphinx-doc.org>"), (46, 48, "`_")],
        )
        self.assertEqual(
            highlight_string(
                "Hello `world <https://weblate.org>`_", unit, highlight_syntax=True
            ),
            [(6, 7, "`"), (13, 34, "<https://weblate.org>"), (34, 36, "`_")],
        )
        self.assertEqual(
            highlight_string("Hello **world**", unit, highlight_syntax=True),
            [(6, 8, "**"), (13, 15, "**")],
        )
        self.assertEqual(
            highlight_string("Hello *world*", unit, highlight_syntax=True),
            [(6, 7, "*"), (12, 13, "*")],
        )
        self.assertEqual(
            highlight_string(":guilabel:`Hello`", unit, highlight_syntax=True),
            [(0, 11, ":guilabel:`"), (16, 17, "`")],
        )
        self.assertEqual(
            highlight_string(":Code:`printf()`", unit, highlight_syntax=True),
            [(0, 7, ":Code:`"), (15, 16, "`")],
        )
        self.assertEqual(
            highlight_string("`printf()`:Code:", unit, highlight_syntax=True),
            [(0, 1, "`"), (9, 16, "`:Code:")],
        )
        self.assertEqual(
            highlight_string(":file:`/tmp/example.txt`", unit, highlight_syntax=True),
            [(0, 7, ":file:`"), (23, 24, "`")],
        )
        self.assertEqual(
            highlight_string(":code:`printf()`", unit, highlight_syntax=True),
            [(0, 7, ":code:`"), (15, 16, "`")],
        )
        self.assertEqual(
            highlight_string(":math:`x + y`", unit, highlight_syntax=True),
            [(0, 7, ":math:`"), (12, 13, "`")],
        )
        self.assertEqual(
            highlight_string(":sub:`2`", unit, highlight_syntax=True),
            [(0, 6, ":sub:`"), (7, 8, "`")],
        )
        self.assertEqual(
            highlight_string(":sup:`2`", unit, highlight_syntax=True),
            [(0, 6, ":sup:`"), (7, 8, "`")],
        )
        self.assertEqual(
            highlight_string(
                ":ref:`review workflow <reviews>`", unit, highlight_syntax=True
            ),
            [(0, 6, ":ref:`"), (21, 32, " <reviews>`")],
        )
        self.assertEqual(
            highlight_string(
                "`review workflow <reviews>`:ref:",
                unit,
                highlight_syntax=True,
            ),
            [(0, 1, "`"), (16, 32, " <reviews>`:ref:")],
        )

    def test_rst_duplicate_fragment(self) -> None:
        unit = make_unit(
            source="Use ``:ref:`foo``` syntax, then see :ref:`foo`.",
            flags="rst-text",
        )
        self.assertEqual(
            highlight_string(
                "Use ``:ref:`foo``` syntax, then see :ref:`foo`.",
                unit,
            ),
            [(36, 46, ":ref:`foo`")],
        )

    def test_rst_escaped_role_example(self) -> None:
        unit = make_unit(
            source=r"Use \:ref:`foo` literally, then see :ref:`foo`.",
            flags="rst-text",
        )
        self.assertEqual(
            highlight_string(
                r"Use \:ref:`foo` literally, then see :ref:`foo`.",
                unit,
            ),
            [(36, 46, ":ref:`foo`")],
        )

    def test_escaped_markup(self) -> None:
        unit = make_unit(
            source="&lt;strong&gt;Not limit the amount of videos&lt;/strong&gt; new users can upload",
            flags='icu-message-format, placeholders:r"&lt;[a-z/]+&gt;", xml-text',
        )
        self.assertEqual(
            highlight_string(unit.source, unit, highlight_syntax=True),
            [
                (0, 14, "&lt;strong&gt;"),
                (44, 59, "&lt;/strong&gt;"),
            ],
        )

    def test_replace_highlighted(self) -> None:
        unit = make_unit(
            source="simple {format} %d string",
            flags="python-brace-format, python-format",
        )
        self.assertEqual(
            replace_highlighted(unit.source, unit),
            "simple   string",
        )
        self.assertEqual(
            replace_highlighted(
                unit.source,
                unit,
                lambda start: f"x-weblate-{start}",
            ),
            "simple x-weblate-7 x-weblate-16 string",
        )

    def test_replace_highlighted_callable_not_cached(self) -> None:
        unit = make_unit(
            source="simple {format} string",
            flags="python-brace-format",
        )
        calls = []

        def replace_first(start):
            calls.append(("first", start))
            return "first"

        def replace_second(start):
            calls.append(("second", start))
            return "second"

        self.assertEqual(
            replace_highlighted(unit.source, unit, replace_first),
            "simple first string",
        )
        self.assertNotIn("_replace_highlighted_cache", unit.__dict__)
        self.assertEqual(
            replace_highlighted(unit.source, unit, replace_second),
            "simple second string",
        )
        self.assertEqual(calls, [("first", 7), ("second", 7)])

    def test_replace_highlighted_module_function_cached(self) -> None:
        unit = make_unit(
            source="simple {format} string",
            flags="python-brace-format",
        )
        REPLACEMENT_CALLS.clear()

        self.assertEqual(
            replace_highlighted(unit.source, unit, marker_replacement),
            "simple marker-7 string",
        )
        self.assertEqual(
            replace_highlighted(unit.source, unit, marker_replacement),
            "simple marker-7 string",
        )
        self.assertEqual(REPLACEMENT_CALLS, [7])

    def test_replace_highlighted_cache_uses_current_flags(self) -> None:
        unit = make_unit(source="simple {format} string", flags="")

        self.assertEqual(
            replace_highlighted(unit.source, unit),
            "simple {format} string",
        )
        set_unit_flags(unit, "python-brace-format")
        self.assertEqual(
            replace_highlighted(unit.source, unit),
            "simple  string",
        )

    def test_replace_highlighted_rst_without_syntax(self) -> None:
        """Without highlight_syntax, RST inline literals are not stripped."""
        unit = make_unit(source="``release``", flags="rst-text")
        # highlight_string with default highlight_syntax=False finds no highlights
        # for RST markup, so the source is returned unchanged.
        self.assertEqual(
            replace_highlighted(unit.source, unit),
            "``release``",
        )

    def test_replace_highlighted_rst_with_syntax(self) -> None:
        """
        With highlight_syntax=True, RST inline literal content is stripped.

        highlight_pygments yields the inner text and surrounding backtick tokens
        as separate spans, so the translatable word inside is removed.  The
        surviving characters (the second `` ` `` of the opening marker) are
        punctuation-only and not meaningful to SameCheck.
        """
        unit = make_unit(source="``release``", flags="rst-text")
        result = replace_highlighted(unit.source, unit, highlight_syntax=True)
        # The inner word must be gone - only punctuation may remain.
        self.assertNotIn("release", result)

    def test_replace_highlighted_rst_role_with_syntax(self) -> None:
        """With highlight_syntax=True, RST :role:`...` spans are stripped."""
        unit = make_unit(source=":ref:`index`", flags="rst-text")
        self.assertEqual(
            replace_highlighted(unit.source, unit, highlight_syntax=True),
            "",
        )
