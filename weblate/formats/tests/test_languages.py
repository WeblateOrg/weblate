# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Explicit language declarations in uploaded files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.test import SimpleTestCase

from weblate.formats.base import MAX_DECLARED_LANGUAGES
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.ttkit import (
    ARBFormat,
    JSONFormat,
    PoFormat,
    TS1Format,
    TS2Format,
    Xliff2Format,
    XliffFormat,
)

if TYPE_CHECKING:
    from weblate.formats.base import TranslationFormat


class DeclaredLanguagesTest(SimpleTestCase):
    def test_declared_languages(self) -> None:
        cases: tuple[tuple[type[TranslationFormat], bytes, set[str], set[str]], ...] = (
            (PoFormat, b'msgid ""\nmsgstr "Language: de\\n"\n', {"de"}, set()),
            (PoFormat, b'msgid ""\nmsgstr "Language-Team: German\\n"\n', set(), set()),
            (
                XliffFormat,
                b'<xliff version="1.2"><file source-language="en" target-language="de"><body/></file><file target-language="fr"><body/></file></xliff>',
                {"de", "fr"},
                {"en"},
            ),
            (
                XliffFormat,
                b'<xliff version="1.2"><file><body/></file></xliff>',
                set(),
                set(),
            ),
            (
                Xliff2Format,
                b'<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0" version="2.0" srcLang="en" trgLang="de"><file id="f"/></xliff>',
                {"de"},
                {"en"},
            ),
            (
                Xliff2Format,
                b'<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0" version="2.0"><file id="f"/></xliff>',
                set(),
                set(),
            ),
            (TS1Format, b'<TS language="de" sourcelanguage="en"/>', {"de"}, {"en"}),
            (
                TS2Format,
                b'<TS version="2.1" language="de" sourcelanguage="en"/>',
                {"de"},
                {"en"},
            ),
            (TS2Format, b'<TS version="2.1"/>', set(), set()),
            (ARBFormat, b'{"@@locale": "de", "hello": "Hallo"}', {"de"}, set()),
            (ARBFormat, b'{"@@locale": 42, "hello": "Hallo"}', set(), set()),
            (JSONFormat, b'{"hello": "Hallo"}', set(), set()),
        )
        for format_class, content, target, source in cases:
            with self.subTest(format=format_class, content=content):
                # Destination settings must never masquerade as file metadata.
                store = format_class(
                    NamedBytesIO("test", content),
                    language_code="cs",
                    source_language="es",
                )
                self.assertEqual(store.get_declared_languages(), target)
                self.assertEqual(store.get_declared_languages(source=True), source)

    def test_xliff_declared_languages_are_bounded(self) -> None:
        files = b"".join(
            f'<file target-language="x-{index}"><body/></file>'.encode()
            for index in range(MAX_DECLARED_LANGUAGES + 2)
        )
        store = XliffFormat(
            NamedBytesIO("test.xlf", b'<xliff version="1.2">' + files + b"</xliff>")
        )

        self.assertEqual(
            len(store.get_declared_languages()), MAX_DECLARED_LANGUAGES + 1
        )
