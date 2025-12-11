# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from weblate.checks.flags import TYPED_FLAGS, TYPED_FLAGS_ARGS, Flags, FlagsValidator
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.ttkit import PoFormat
from weblate.trans.defines import VARIANT_KEY_LENGTH

PO_HEADER = r"""
msgid ""
msgstr ""
"Project-Id-Version: Weblate Hello World 2012\n"
"Report-Msgid-Bugs-To: <noreply@example.net>\n"
"POT-Creation-Date: 2012-03-14 15:54+0100\n"
"PO-Revision-Date: 2013-08-25 15:23+0200\n"
"Last-Translator: testuser <>\n"
"Language-Team: Czech <http://example.com/projects/test/test/cs/>\n"
"Language: cs\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Plural-Forms: nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;\n"
"X-Generator: Weblate 1.7-dev\n"


"""


class FlagTest(SimpleTestCase):
    def test_parse(self) -> None:
        self.assertEqual(Flags("foo, bar").items(), {"foo", "bar"})

    def test_parse_blank(self) -> None:
        self.assertEqual(Flags("foo, bar, ").items(), {"foo", "bar"})

    def test_parse_alias(self) -> None:
        self.assertEqual(
            Flags("foo, md-text, bar, markdown-text").items(), {"foo", "bar", "md-text"}
        )

    def test_iter(self) -> None:
        self.assertEqual(sorted(Flags("foo, bar")), ["bar", "foo"])

    def test_has_any(self) -> None:
        flags = Flags("foo, bar")
        self.assertFalse(flags.has_any(set()))
        self.assertFalse(flags.has_any({"baz"}))
        self.assertTrue(flags.has_any({"bar", "foo"}))
        self.assertTrue(flags.has_any({"bar", "baz"}))

    def test_parse_empty(self) -> None:
        self.assertEqual(Flags("").items(), set())

    def test_merge(self) -> None:
        self.assertEqual(Flags({"foo"}, {"bar"}).items(), {"foo", "bar"})

    def test_merge_prefix(self) -> None:
        self.assertEqual(Flags({("foo", "1")}, {("foo", "2")}).items(), {("foo", "2")})

    def test_values(self) -> None:
        flags = Flags("placeholders:bar:baz")
        self.assertEqual(flags.get_value("placeholders"), ["bar", "baz"])

    def test_quoted_values(self) -> None:
        flags = Flags(r"""placeholders:"bar: \"value\"":'baz \'value\''""")
        self.assertEqual(
            flags.get_value("placeholders"), ['bar: "value"', "baz 'value'"]
        )
        self.assertEqual(
            flags.format(), r'''placeholders:"bar: \"value\"":"baz 'value'"'''
        )
        flags = Flags(r'regex:"((?:@:\(|\{)[^\)\}]+(?:\)|\}))"')
        self.assertEqual(flags.format(), r'regex:"((?:@:\(|\{)[^\)\}]+(?:\)|\}))"')

    def test_newline(self) -> None:
        flags = Flags(r"""placeholders:"\n" """)
        self.assertEqual(flags.get_value("placeholders"), ["\n"])

    def test_validate_value(self) -> None:
        with self.assertRaises(ValidationError):
            Flags("max-length:x").validate()
        Flags("max-length:30").validate()

    def test_validate_name(self) -> None:
        with self.assertRaises(ValidationError):
            Flags("invalid-check-name").validate()
        with self.assertRaises(ValidationError):
            Flags("invalid-check-name:1").validate()
        Flags("ignore-max-length").validate()

    def test_typed(self) -> None:
        self.assertEqual(TYPED_FLAGS.keys(), TYPED_FLAGS_ARGS.keys())

    def test_remove(self) -> None:
        flags = Flags("placeholders:bar:baz, foo:1, bar")
        flags.remove("foo")
        self.assertEqual(flags.items(), {("placeholders", "bar", "baz"), "bar"})
        flags.remove("bar")
        self.assertEqual(flags.items(), {("placeholders", "bar", "baz")})

    def test_empty_value(self) -> None:
        flags = Flags("regex:")
        regex = flags.get_value("regex")
        self.assertEqual(regex.pattern, "")
        flags = Flags("regex:,bar")
        regex = flags.get_value("regex")
        self.assertEqual(regex.pattern, "")

    def test_regex(self) -> None:
        flags = Flags("regex:.*")
        regex = flags.get_value("regex")
        self.assertEqual(regex.pattern, ".*")
        flags = Flags('regex:r".*"')
        regex = flags.get_value("regex")
        self.assertEqual(regex.pattern, ".*")

    def test_regex_value(self) -> None:
        flags = Flags("placeholders:r")
        self.assertEqual(flags.get_value("placeholders"), ["r"])
        flags = Flags("placeholders:r:r")
        self.assertEqual(flags.get_value("placeholders"), ["r", "r"])
        flags = Flags("placeholders:r,r")
        self.assertEqual(flags.get_value("placeholders"), ["r"])
        flags = Flags('placeholders:r".*"')
        values = flags.get_value("placeholders")
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].pattern, ".*")
        self.assertEqual(flags.format(), 'placeholders:r".*"')

    def test_whitespace(self) -> None:
        self.assertEqual(Flags("  foo    , bar  ").items(), {"foo", "bar"})
        flags = Flags(
            "max-size:120:2,font-family:DIN next pro,font-spacing:2, priority:140"
        )
        self.assertEqual(
            flags.items(),
            {
                ("font-family", "DIN next pro"),
                ("priority", "140"),
                ("max-size", "120", "2"),
                ("font-spacing", "2"),
            },
        )
        self.assertEqual(
            Flags("font-family: segoeui").items(), {("font-family", "segoeui")}
        )

    def test_unicode(self) -> None:
        self.assertEqual(
            Flags("zkouška, Memóriakártya").items(), {"zkouška", "Memóriakártya"}
        )
        self.assertEqual(
            Flags("placeholder:'zkouška sirén'").items(),
            {("placeholder", "zkouška sirén")},
        )

    def test_replacements(
        self, text='replacements:{COLOR-GREY}:"":{COLOR-GARNET}:"":{VARIABLE-01}:99'
    ) -> None:
        flags = Flags(text)
        self.assertEqual(
            flags.items(),
            {
                (
                    "replacements",
                    "{COLOR-GREY}",
                    "",
                    "{COLOR-GARNET}",
                    "",
                    "{VARIABLE-01}",
                    "99",
                )
            },
        )
        self.assertEqual(
            flags.get_value("replacements"),
            ["{COLOR-GREY}", "", "{COLOR-GARNET}", "", "{VARIABLE-01}", "99"],
        )

    def test_empty_params(self) -> None:
        self.test_replacements(
            "replacements:{COLOR-GREY}::{COLOR-GARNET}::{VARIABLE-01}:99"
        )

    def test_escaped_values(self) -> None:
        flags = Flags(r"""placeholders:"\\":"\"" """)
        self.assertEqual(flags.get_value("placeholders"), ["\\", '"'])

    def test_set(self) -> None:
        flags = Flags()
        flags.set_value("variant", "Long string with \"quotes\" and 'quotes'.")
        self.assertEqual(
            flags.format(), r'''variant:"Long string with \"quotes\" and 'quotes'."'''
        )

    def test_validate_variant(self) -> None:
        name = "x" * VARIANT_KEY_LENGTH
        Flags(f"variant:{name}").validate()
        name = "x" * (VARIANT_KEY_LENGTH + 1)
        with self.assertRaises(ValidationError):
            Flags(f"variant:{name}").validate()

    def test_windows_path(self) -> None:
        flags = Flags(r"Scripts\Tscripts\pages\dist\grplus.js:1046")
        self.assertEqual(
            flags.format(), r'"Scripts\Tscripts\pages\dist\grplus.js":1046'
        )

    def test_discard(self) -> None:
        flags = Flags("foo", "discard:foo")
        self.assertEqual(flags.format(), "")
        flags = Flags("foo", "discard:bar")
        self.assertEqual(flags.format(), "foo")

    def test_discard_validator(self) -> None:
        flags = FlagsValidator("foo", "discard:foo")
        self.assertEqual(flags.format(), "discard:foo, foo")
        flags = FlagsValidator("foo", "discard:bar")
        self.assertEqual(flags.format(), "discard:bar, foo")
        flags = FlagsValidator("discard:bar")
        with self.assertRaises(ValidationError):
            flags.validate()
        flags = FlagsValidator("discard")
        with self.assertRaises(ValidationError):
            flags.validate()
        flags = FlagsValidator("discard:ignore-same")
        flags.validate()

    def test_equals(self) -> None:
        from lxml import etree

        flags = Flags("foo:foo, bar:bar")
        self.assertEqual(flags, Flags("bar:bar, foo:foo"))
        self.assertEqual(flags, Flags(Flags("bar:bar, foo:foo")))
        self.assertEqual(flags, Flags("bar:bar, foo:foo"))

        flags_xml = etree.fromstring(
            """<flags weblate-flags="bar:bar, foo:foo"></flags>"""
        )
        self.assertEqual(flags, Flags(flags_xml))

        flags = Flags(None)
        self.assertEqual(flags, Flags())
        self.assertEqual(flags, Flags(""))
        self.assertEqual(flags, Flags(None))

    def test_automatic_location_flags(self) -> None:
        def check_location_flags(content: str, expected_flags: set[str]) -> None:
            fileformat = PoFormat(NamedBytesIO("", content.encode()))
            flags = list(fileformat.all_units)[0].flags  # noqa: RUF015
            self.assertEqual(set(flags), expected_flags)

        # test rst-text flag
        content = PO_HEADER + (
            "#: ../../path/file.rst:24 ../../path/file.rst:52"
            "#: ../../path/file.rst:63"
            'msgid "Hello, world!"'
            'msgstr "Nazdar svete!"'
        )
        check_location_flags(content, {"rst-text"})

        # test md-text flag
        content = PO_HEADER + (
            "#: ../../path/file.md:24 ../../path/file.md:52"
            'msgid "Hello, world!"'
            'msgstr "Nazdar svete!"'
        )
        check_location_flags(content, {"md-text"})
