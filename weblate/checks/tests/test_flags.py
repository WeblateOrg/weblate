# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from weblate.checks.flags import TYPED_FLAGS, TYPED_FLAGS_ARGS, Flags
from weblate.trans.defines import VARIANT_KEY_LENGTH


class FlagTest(SimpleTestCase):
    def test_parse(self):
        self.assertEqual(Flags("foo, bar").items(), {"foo", "bar"})

    def test_parse_blank(self):
        self.assertEqual(Flags("foo, bar, ").items(), {"foo", "bar"})

    def test_parse_alias(self):
        self.assertEqual(
            Flags("foo, md-text, bar, markdown-text").items(), {"foo", "bar", "md-text"}
        )

    def test_iter(self):
        self.assertEqual(sorted(Flags("foo, bar")), ["bar", "foo"])

    def test_parse_empty(self):
        self.assertEqual(Flags("").items(), set())

    def test_merge(self):
        self.assertEqual(Flags({"foo"}, {"bar"}).items(), {"foo", "bar"})

    def test_merge_prefix(self):
        self.assertEqual(Flags({("foo", "1")}, {("foo", "2")}).items(), {("foo", "2")})

    def test_values(self):
        flags = Flags("placeholders:bar:baz")
        self.assertEqual(flags.get_value("placeholders"), ["bar", "baz"])

    def test_quoted_values(self):
        flags = Flags(r"""placeholders:"bar: \"value\"":'baz \'value\''""")
        self.assertEqual(
            flags.get_value("placeholders"), ['bar: "value"', "baz 'value'"]
        )
        self.assertEqual(
            flags.format(), r'''placeholders:"bar: \"value\"":"baz 'value'"'''
        )
        flags = Flags(r'regex:"((?:@:\(|\{)[^\)\}]+(?:\)|\}))"')
        self.assertEqual(flags.format(), r'regex:"((?:@:\(|\{)[^\)\}]+(?:\)|\}))"')

    def test_newline(self):
        flags = Flags(r"""placeholders:"\n" """)
        self.assertEqual(flags.get_value("placeholders"), ["\n"])

    def test_validate_value(self):
        with self.assertRaises(ValidationError):
            Flags("max-length:x").validate()
        Flags("max-length:30").validate()

    def test_validate_name(self):
        with self.assertRaises(ValidationError):
            Flags("invalid-check-name").validate()
        with self.assertRaises(ValidationError):
            Flags("invalid-check-name:1").validate()
        Flags("ignore-max-length").validate()

    def test_typed(self):
        self.assertEqual(TYPED_FLAGS.keys(), TYPED_FLAGS_ARGS.keys())

    def test_remove(self):
        flags = Flags("placeholders:bar:baz, foo:1, bar")
        flags.remove("foo")
        self.assertEqual(flags.items(), {("placeholders", "bar", "baz"), "bar"})
        flags.remove("bar")
        self.assertEqual(flags.items(), {("placeholders", "bar", "baz")})

    def test_empty_value(self):
        flags = Flags("regex:")
        regex = flags.get_value("regex")
        self.assertEqual(regex.pattern, "")
        flags = Flags("regex:,bar")
        regex = flags.get_value("regex")
        self.assertEqual(regex.pattern, "")

    def test_regex(self):
        flags = Flags("regex:.*")
        regex = flags.get_value("regex")
        self.assertEqual(regex.pattern, ".*")
        flags = Flags('regex:r".*"')
        regex = flags.get_value("regex")
        self.assertEqual(regex.pattern, ".*")

    def test_regex_value(self):
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

    def test_whitespace(self):
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

    def test_unicode(self):
        self.assertEqual(
            Flags("zkouška, Memóriakártya").items(), {"zkouška", "Memóriakártya"}
        )
        self.assertEqual(
            Flags("placeholder:'zkouška sirén'").items(),
            {("placeholder", "zkouška sirén")},
        )

    def test_replacements(
        self, text='replacements:{COLOR-GREY}:"":{COLOR-GARNET}:"":{VARIABLE-01}:99'
    ):
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

    def test_empty_params(self):
        self.test_replacements(
            "replacements:{COLOR-GREY}::{COLOR-GARNET}::{VARIABLE-01}:99"
        )

    def test_escaped_values(self):
        flags = Flags(r"""placeholders:"\\":"\"" """)
        self.assertEqual(flags.get_value("placeholders"), ["\\", '"'])

    def test_set(self):
        flags = Flags()
        flags.set_value("variant", "Long string with \"quotes\" and 'quotes'.")
        self.assertEqual(
            flags.format(), r'''variant:"Long string with \"quotes\" and 'quotes'."'''
        )

    def test_validate_variant(self):
        name = "x" * VARIANT_KEY_LENGTH
        Flags(f"variant:{name}").validate()
        name = "x" * (VARIANT_KEY_LENGTH + 1)
        with self.assertRaises(ValidationError):
            Flags(f"variant:{name}").validate()
