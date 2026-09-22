# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for automatic fixups."""

from __future__ import annotations

from django.test import TestCase

from weblate.trans.autofixes import fix_target
from weblate.trans.autofixes.chars import (
    DevanagariDanda,
    PunctuationSpacing,
    RemoveControlChars,
    RemoveZeroSpace,
    ReplaceTrailingDotsWithEllipsis,
)
from weblate.trans.autofixes.custom import DoubleApostrophes
from weblate.trans.autofixes.html import BleachHTML
from weblate.trans.autofixes.whitespace import SameBookendingWhitespace
from weblate.trans.tests.factories import make_unit, set_unit_flags, set_unit_source


class AutoFixTest(TestCase):
    def test_multivalue_conflicting_source_autofixes(self) -> None:
        cases = (
            (
                SameBookendingWhitespace(),
                [" app ", "application"],
                ["aplikace", " program "],
            ),
            (
                ReplaceTrailingDotsWithEllipsis(),
                ["app…", "application"],
                ["aplikace...", "program"],
            ),
            (
                RemoveZeroSpace(),
                ["app\u200b", "application"],
                ["aplikace\u200b", "program"],
            ),
        )
        for file_format in ("tbx", "csv-multi"):
            for fix, sources, targets in cases:
                for source_order in (sources, sources[::-1]):
                    with self.subTest(
                        file_format=file_format, fix=fix.fix_id, sources=source_order
                    ):
                        unit = make_unit(source=source_order)
                        unit.translation.component.file_format = file_format
                        self.assertEqual(
                            fix.fix_target(targets, unit), (targets, False)
                        )

    def test_multivalue_unambiguous_autofixes(self) -> None:
        for file_format in ("tbx", "csv-multi"):
            for sources in ([" app "], [" app ", " application "]):
                with self.subTest(file_format=file_format, sources=sources):
                    unit = make_unit(source=sources)
                    unit.translation.component.file_format = file_format
                    self.assertEqual(
                        SameBookendingWhitespace().fix_target(
                            ["aplikace", "program"], unit
                        ),
                        ([" aplikace ", " program "], True),
                    )

    def test_multivalue_source_independent_autofixes(self) -> None:
        for file_format in ("tbx", "csv-multi"):
            with self.subTest(file_format=file_format):
                unit = make_unit(source=[" app ", "application"])
                unit.translation.component.file_format = file_format
                fixed, fixes = fix_target(["aplikace\x1b", " program "], unit)
                self.assertEqual(fixed, ["aplikace", " program "])
                self.assertEqual([str(fix) for fix in fixes], ["Control characters"])

    def test_ellipsis(self) -> None:
        unit = make_unit(source="Foo…")
        fix = ReplaceTrailingDotsWithEllipsis()
        self.assertEqual(fix.fix_target(["Bar..."], unit), (["Bar…"], True))
        self.assertEqual(fix.fix_target(["Bar... "], unit), (["Bar... "], False))

    def test_no_ellipsis(self) -> None:
        unit = make_unit(source="Foo...")
        fix = ReplaceTrailingDotsWithEllipsis()
        self.assertEqual(fix.fix_target(["Bar..."], unit), (["Bar..."], False))
        self.assertEqual(fix.fix_target(["Bar…"], unit), (["Bar…"], False))

    def test_whitespace(self) -> None:
        unit = make_unit(source="Foo\n")
        fix = SameBookendingWhitespace()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar\n"], True))
        self.assertEqual(fix.fix_target(["Bar\n"], unit), (["Bar\n"], False))
        unit = make_unit(source=" ")
        self.assertEqual(fix.fix_target(["  "], unit), (["  "], False))

    def test_no_whitespace(self) -> None:
        unit = make_unit(source="Foo")
        fix = SameBookendingWhitespace()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\n"], unit), (["Bar"], True))

    def test_whitespace_flags(self) -> None:
        fix = SameBookendingWhitespace()
        unit = make_unit(source="str", flags="ignore-begin-space")
        self.assertEqual(fix.fix_target(["  str"], unit), (["  str"], False))
        unit = make_unit(source="str", flags="ignore-end-space")
        self.assertEqual(fix.fix_target(["  str  "], unit), (["str  "], True))

    def test_html(self) -> None:
        fix = BleachHTML()
        unit = make_unit(source='<a href="script:foo()">link</a>', flags="safe-html")
        self.assertEqual(
            fix.fix_target(['<a href="script:foo()">link</a>'], unit),
            (["<a>link</a>"], True),
        )
        self.assertEqual(
            fix.fix_target(['<a href="#" onclick="foo()">link</a>'], unit),
            (['<a href="#">link</a>'], True),
        )
        self.assertEqual(
            fix.fix_target(["<https://weblate.org>"], unit),
            ([""], True),
        )
        self.assertEqual(
            fix.fix_target(["%(percent)s %%"], unit),
            (["%(percent)s %%"], False),
        )

    def test_html_ignored(self) -> None:
        fix = BleachHTML()
        unit = make_unit(
            source='<a href="script:foo()">link</a>', flags="safe-html,ignore-safe-html"
        )
        self.assertEqual(
            fix.fix_target(["Allow <b>"], unit),
            (["Allow <b>"], False),
        )

    def test_html_markdown(self) -> None:
        fix = BleachHTML()
        unit = make_unit(
            source='<a href="script:foo()">link</a>', flags="safe-html,md-text"
        )
        self.assertEqual(
            fix.fix_target(
                ['<a href="script:foo()">link</a><https://weblate.org>'], unit
            ),
            (["<a>link</a><https://weblate.org>"], True),
        )
        self.assertEqual(
            fix.fix_target(["<https://weblate.org>"], unit),
            (["<https://weblate.org>"], False),
        )

    def test_html_mdx_void_element(self) -> None:
        value = "Paragraph.<br />"
        fix = BleachHTML()
        unit = make_unit(source=value, flags="auto-safe-html,md-text,safe-mdx")
        self.assertEqual(fix.fix_target([value], unit), ([value], False))
        self.assertEqual(
            fix.fix_target(["Paragraph.<br>"], unit),
            ([value], True),
        )

    def test_auto_safe_html(self) -> None:
        fix = BleachHTML()
        unit = make_unit(source="link", flags="auto-safe-html")
        self.assertEqual(
            fix.fix_target(["<b>link</b>"], unit),
            (["link"], True),
        )
        unit = make_unit(source="Press <b to continue", flags="auto-safe-html")
        self.assertEqual(
            fix.fix_target(["<script>alert(1)</script>"], unit),
            (["<script>alert(1)</script>"], False),
        )
        unit = make_unit(
            source='<a href="https://weblate.org">link</a>', flags="auto-safe-html"
        )
        self.assertEqual(
            fix.fix_target(['<a href="javascript:foo()">link</a>'], unit),
            (["<a>link</a>"], True),
        )
        unit = make_unit(source="<x-demo>link</x-demo>", flags="auto-safe-html")
        self.assertEqual(
            fix.fix_target(['<x-demo onclick="alert(1)">link</x-demo>'], unit),
            (["<x-demo>link</x-demo>"], True),
        )
        unit = make_unit(source='<a title="1 > 0">link</a>', flags="auto-safe-html")
        self.assertEqual(
            fix.fix_target(['<a title="1 > 0" href="javascript:foo()">link</a>'], unit),
            (['<a title="1 &gt; 0">link</a>'], True),
        )
        unit = make_unit(source='<a title="a<b">link</a>', flags="auto-safe-html")
        self.assertEqual(
            fix.fix_target(['<a title="a<b" href="javascript:foo()">link</a>'], unit),
            (['<a title="a&lt;b">link</a>'], True),
        )
        unit = make_unit(source="Line<br/>break", flags="auto-safe-html")
        self.assertEqual(
            fix.fix_target(["Line<script>alert(1)</script>break"], unit),
            (["Linebreak"], True),
        )
        unit = make_unit(source="<option selected>", flags="auto-safe-html")
        self.assertEqual(
            fix.fix_target(["<script>alert(1)</script>"], unit),
            (["<script>alert(1)</script>"], False),
        )

    def test_auto_safe_html_markdown_component(self) -> None:
        fix = BleachHTML()
        value = "<TOCInline toc={toc.filter((node)) => node.level === 2)} />"
        unit = make_unit(source=value, flags="auto-safe-html,md-text")
        self.assertEqual(fix.fix_target([value], unit), ([value], False))

    def test_auto_safe_html_safe_html_wins(self) -> None:
        fix = BleachHTML()
        value = "<TOCInline toc={toc.filter((node)) => node.level === 2)} />"
        unit = make_unit(source=value, flags="auto-safe-html,md-text,safe-html")
        self.assertEqual(
            fix.fix_target(["<script>alert(1)</script>"], unit),
            ([""], True),
        )

    def test_zerospace(self) -> None:
        unit = make_unit(source="Foo\u200b")
        fix = RemoveZeroSpace()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\u200b"], unit), (["Bar\u200b"], False))

    def test_no_zerospace(self) -> None:
        unit = make_unit(source="Foo")
        fix = RemoveZeroSpace()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\u200b"], unit), (["Bar"], True))

    def test_controlchars(self) -> None:
        unit = make_unit(source="Foo\x1b")
        fix = RemoveControlChars()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\x1b"], unit), (["Bar"], True))
        self.assertEqual(fix.fix_target(["Bar\n"], unit), (["Bar\n"], False))

    def test_no_controlchars(self) -> None:
        unit = make_unit(source="Foo")
        fix = RemoveControlChars()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\x1b"], unit), (["Bar"], True))
        self.assertEqual(fix.fix_target(["Bar\n"], unit), (["Bar\n"], False))

    def test_fix_target(self) -> None:
        unit = make_unit(source="Foo…")
        fixed, fixups = fix_target(["Bar..."], unit)
        self.assertEqual(fixed, ["Bar…"])
        self.assertEqual(len(fixups), 1)
        self.assertEqual(str(fixups[0]), "Trailing ellipsis")

    def test_apostrophes(self) -> None:
        unit = make_unit(source="Foo")
        fix = DoubleApostrophes()
        # No flags
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        # No format string, but forced
        set_unit_flags(unit, "java-format")
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        # No format string
        set_unit_flags(unit, "auto-java-messageformat")
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        set_unit_source(unit, "{0,number}")
        self.assertEqual(fix.fix_target(["bar'"], unit), (["bar''"], True))
        set_unit_flags(unit, "auto-java-messageformat,ignore-java-format")
        self.assertEqual(fix.fix_target(["bar'"], unit), (["bar'"], False))
        set_unit_flags(unit, "auto-java-messageformat")
        set_unit_source(unit, "test {0}")
        # Nothing to fix
        self.assertEqual(fix.fix_target(["r {0}"], unit), (["r {0}"], False))
        # Correct string
        self.assertEqual(fix.fix_target(["''r'' {0}"], unit), (["''r'' {0}"], False))
        # String with quoted format string
        self.assertEqual(
            fix.fix_target(["''r'' '{0}'"], unit), (["''r'' '{0}'"], False)
        )
        # Fixes
        self.assertEqual(fix.fix_target(["'r''' {0}"], unit), (["''r'' {0}"], True))
        # Fixes keeping double ones
        self.assertEqual(
            fix.fix_target(["'''''''r'''' {0}"], unit), (["''''r'''' {0}"], True)
        )
        # Quoted format
        self.assertEqual(fix.fix_target(["'r''' {0}"], unit), (["''r'' {0}"], True))
        set_unit_source(unit, "foo")
        set_unit_flags(unit, "java-format")
        self.assertEqual(fix.fix_target(["bar'"], unit), (["bar''"], True))

    def test_devanagaridanda(self) -> None:
        non_unit = make_unit(source="Foo", code="bn")
        bn_unit = make_unit(source="Foo.", code="bn")
        cs_unit = make_unit(source="Foo.", code="cs")
        fix = DevanagariDanda()
        self.assertEqual(fix.fix_target(["Bar."], non_unit), (["Bar."], False))
        self.assertEqual(fix.fix_target(["Bar."], bn_unit), (["Bar।"], True))
        self.assertEqual(fix.fix_target(["Bar|"], bn_unit), (["Bar।"], True))
        self.assertEqual(fix.fix_target(["Bar।"], bn_unit), (["Bar।"], False))
        self.assertEqual(fix.fix_target(["Bar."], cs_unit), (["Bar."], False))

    def test_punctuation_spacing(self) -> None:
        fix = PunctuationSpacing()
        non_unit = make_unit(source="Foo", code="bn")
        fr_unit = make_unit(source="Foo:", code="fr")
        fr_ca_unit = make_unit(source="Foo:", code="fr_CA")
        cs_unit = make_unit(source="Foo:", code="cs")
        self.assertEqual(fix.fix_target(["Bar:"], non_unit), (["Bar:"], False))
        self.assertEqual(
            fix.fix_target(["Bar\u00a0:"], fr_unit), (["Bar\u00a0:"], False)
        )
        self.assertEqual(fix.fix_target(["Bar :"], fr_unit), (["Bar\u00a0:"], True))
        self.assertEqual(fix.fix_target(["Bar:"], fr_unit), (["Bar:"], False))
        self.assertEqual(fix.fix_target(["Bar:"], fr_ca_unit), (["Bar:"], False))
        self.assertEqual(fix.fix_target(["Bar:"], cs_unit), (["Bar:"], False))

    def test_punctuation_spacing_rst(self) -> None:
        fix = PunctuationSpacing()
        fr_rst_unit = make_unit(source="This :ref:`doc`", code="fr", flags="rst-text")
        self.assertEqual(
            fix.fix_target(["This :ref:`doc`"], fr_rst_unit),
            (["This :ref:`doc`"], False),
        )
        self.assertEqual(
            fix.fix_target(["This :"], fr_rst_unit), (["This\u00a0:"], True)
        )

    def test_punctuation_spacing_xliff(self) -> None:
        fix = PunctuationSpacing()
        xliff_flag = r'placeholders:r"<x\s[^>]*/>"'
        # target with ' :' inside equiv-text, should not be modified
        fr_xliff_unit = make_unit(
            source='Quota <x id="INTERPOLATION" equiv-text="{{ quota | bytes : 0 }}"/> par jour',
            code="fr",
            flags=xliff_flag,
        )
        self.assertEqual(
            fix.fix_target(
                [
                    'Quota <x id="INTERPOLATION" equiv-text="{{ quota | bytes : 0 }}"/> par jour'
                ],
                fr_xliff_unit,
            ),
            (
                [
                    'Quota <x id="INTERPOLATION" equiv-text="{{ quota | bytes : 0 }}"/> par jour'
                ],
                False,
            ),
        )

        # ' :' outside a placeholder must still be fixed.
        fr_xliff_unit2 = make_unit(
            source='Quota: <x id="INTERPOLATION" equiv-text="{{ count }}"/> items',
            code="fr",
            flags=xliff_flag,
        )
        self.assertEqual(
            fix.fix_target(
                ['Quota : <x id="INTERPOLATION" equiv-text="{{ count }}"/> éléments'],
                fr_xliff_unit2,
            ),
            (
                [
                    'Quota\u00a0: <x id="INTERPOLATION" equiv-text="{{ count }}"/> éléments'
                ],
                True,
            ),
        )
