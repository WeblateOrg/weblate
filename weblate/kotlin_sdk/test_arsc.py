# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import struct
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import tempfile
import unittest
import zipfile
from pathlib import Path

from weblate.kotlin_sdk.arsc import (
    ResourceTable,
    Text,
    android_text,
    generate,
    locale_config,
)


class ARSCWriterTest(unittest.TestCase):
    def test_whitespace(self) -> None:
        cases = (
            (" a <b> b </b> ", Text(" a  b  ", (("b", 3, 5),))),
            ("  a   <b>  b   </b>   c  ", Text(" a  b  c ", (("b", 3, 5),))),
            (" a\t\n b ", Text("a b")),
            ("\u00a0a\u202fb\u2003", Text("\u00a0a\u202fb\u2003")),
            (' <xliff:g id="x"> a </xliff:g> b ', Text(" a b")),
            (r"\u0020a\u0020", Text(" a ")),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(android_text(raw, markup=True), expected)

    @unittest.skipUnless(os.environ.get("AAPT2"), "Set AAPT2 for compiler comparisons")
    def test_aapt2_whitespace(self) -> None:
        cases = (
            " a <b> b </b> ",
            "  a   <b>  b   </b>   c  ",
            " a\t\n b ",
            "\u00a0a\u202fb\u2003",
            r"\u0020a\u0020",
            ' " a  b " ',
            ' <xliff:g id="x"> a </xliff:g> b ',
            ' a <b> <xliff:g id="x"> b </xliff:g> </b> c ',
            " <b> a <i> b </i> c </b> ",
            " <b>a </b><i> b</i> ",
            " \U0001f600 <b> b </b> ",
            r" a\n <b> b\t </b> ",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = root / "res" / "values-fr"
            values.mkdir(parents=True)
            manifest = root / "AndroidManifest.xml"
            manifest.write_text('<manifest package="org.weblate.sample"/>')

            def run(*args: str) -> str:
                return subprocess.run(
                    [os.environ["AAPT2"], *args],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout

            for raw in cases:
                with self.subTest(raw=raw):
                    (values / "strings.xml").write_text(
                        '<resources xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">'
                        f'<string name="sample">{raw}</string>'
                        f'<plurals name="count"><item quantity="other">{raw}</item></plurals>'
                        "</resources>"
                    )
                    compiled = root / "compiled.zip"
                    apk = root / "compiled.apk"
                    run("compile", "--dir", str(root / "res"), "-o", str(compiled))
                    run(
                        "link",
                        "--no-resource-removal",
                        "--manifest",
                        str(manifest),
                        "-o",
                        str(apk),
                        str(compiled),
                    )
                    expected = run("dump", "resources", str(apk))
                    with zipfile.ZipFile(apk) as archive:
                        binary_manifest = archive.read("AndroidManifest.xml")
                    with zipfile.ZipFile(apk, "w") as archive:
                        archive.writestr("AndroidManifest.xml", binary_manifest)
                        text = android_text(raw, markup=True)
                        archive.writestr(
                            "resources.arsc",
                            generate(
                                "org.weblate.sample",
                                "fr",
                                {
                                    0x7F010000: ("count", {"other": text}),
                                    0x7F020000: ("sample", text),
                                },
                            ),
                        )
                    actual = run("dump", "resources", str(apk))
                    self.assertEqual(
                        [
                            line.strip()
                            for line in actual.splitlines()
                            if line.lstrip().startswith(("(fr)", "other="))
                        ],
                        [
                            line.strip()
                            for line in expected.splitlines()
                            if line.lstrip().startswith(("(fr)", "other="))
                        ],
                    )

    def test_unicode_spans(self) -> None:
        text = android_text("Hello <b>\U0001f600<i>!</i></b>", markup=True)
        self.assertEqual(text.value, "Hello \U0001f600!")
        self.assertEqual(text.spans, (("b", 6, 8), ("i", 8, 8)))

    def test_many_surrogate_spans(self) -> None:
        text = android_text(r"<b>\ud83d\ude00<i>!</i></b> " * 2000, markup=True)
        self.assertEqual(text.value, "\U0001f600! " * 2000)
        self.assertEqual(
            text.spans,
            tuple(
                span
                for index in range(2000)
                for span in (
                    ("b", 4 * index, 4 * index + 2),
                    ("i", 4 * index + 2, 4 * index + 2),
                )
            ),
        )

    def test_literal_markup(self) -> None:
        self.assertEqual(android_text("<b>literal</b>"), Text("<b>literal</b>"))

    def test_nested_span_order(self) -> None:
        text = android_text(
            '<font color="red"><font color="blue">word</font></font>',
            markup=True,
        )
        self.assertEqual(
            text.spans, (("font;color=red", 0, 3), ("font;color=blue", 0, 3))
        )

    def test_escaping(self) -> None:
        self.assertEqual(android_text(r'"  a  b "\n\u00e9'), Text("  a  b \né"))
        self.assertEqual(android_text(" a   b "), Text("a b"))

    def test_invalid_markup(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported Android span"):
            android_text("<unknown>value</unknown>", markup=True)

    def test_locale(self) -> None:
        config = locale_config("b+sr+Latn+RS")
        self.assertEqual(config[8:12], b"srRS")
        self.assertEqual(config[36:40], b"Latn")
        self.assertEqual(locale_config("pt-rBR")[8:12], b"ptBR")

    def test_container_lengths_and_determinism(self) -> None:
        resources: ResourceTable = {
            0x7F090003: ("welcome", Text("Hello")),
            0x7F080012: ("count", {"one": Text("One"), "other": Text("Many")}),
        }
        data = generate("org.weblate.sample", "cs", resources)
        self.assertEqual(struct.unpack_from("<HHII", data), (2, 12, len(data), 1))
        self.assertEqual(data, generate("org.weblate.sample", "cs", resources))
        offset = 12
        while offset < len(data):
            _, header_size, size = struct.unpack_from("<HHI", data, offset)
            self.assertGreaterEqual(size, header_size)
            self.assertEqual(size % 4, 0)
            offset += size
        self.assertEqual(offset, len(data))

    @unittest.skipUnless(
        os.environ.get("AAPT2"), "Set AAPT2 to validate with Android's resource parser"
    )
    def test_android_parser(self) -> None:
        resources: ResourceTable = {
            0x7F090003: ("welcome", android_text("Hello <b>world</b>", markup=True)),
            0x7F080012: ("count", {"one": Text("One"), "other": Text("Many")}),
        }
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "resources.apk"
            manifest = Path(directory) / "AndroidManifest.xml"
            manifest.write_text('<manifest package="org.weblate.sample"/>')
            subprocess.run(
                [
                    os.environ["AAPT2"],
                    "link",
                    "--manifest",
                    str(manifest),
                    "-o",
                    str(apk),
                ],
                check=True,
                capture_output=True,
            )
            with zipfile.ZipFile(apk) as archive:
                manifest_bytes = archive.read("AndroidManifest.xml")
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("AndroidManifest.xml", manifest_bytes)
                archive.writestr(
                    "resources.arsc", generate("org.weblate.sample", "fr", resources)
                )
            result = subprocess.run(
                [os.environ["AAPT2"], "dump", "resources", str(apk)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("0x7f090003", result.stdout)
            self.assertIn("0x7f080012", result.stdout)
            self.assertIn("welcome", result.stdout)
            self.assertIn("Many", result.stdout)
