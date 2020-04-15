#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
        self.assertEqual(Flags({"foo:1"}, {"foo:2"}).items(), {"foo:2"})

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
