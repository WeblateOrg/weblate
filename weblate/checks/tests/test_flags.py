#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from weblate.checks.flags import TYPED_FLAGS, TYPED_FLAGS_ARGS, Flags


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
