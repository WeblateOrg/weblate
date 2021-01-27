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

from weblate.utils.render import validate_editor
from weblate.utils.validators import (
    clean_fullname,
    validate_filename,
    validate_fullname,
    validate_re,
)


class EditorValidatorTest(SimpleTestCase):
    def test_empty(self):
        self.assertIsNone(validate_editor(""))

    def test_valid(self):
        self.assertIsNone(
            validate_editor("editor://open/?file={{ filename }}&line={{ line }}")
        )

    def test_old_format(self):
        with self.assertRaises(ValidationError):
            validate_editor("editor://open/?file=%(file)s&line=%(line)s")

    def test_invalid_format(self):
        with self.assertRaises(ValidationError):
            validate_editor("editor://open/?file={{ fle }}&line={{ line }}")

    def test_no_scheme(self):
        with self.assertRaises(ValidationError):
            validate_editor("./local/url")

    def test_invalid_scheme(self):
        with self.assertRaises(ValidationError):
            validate_editor("javascript:alert(0)")
        with self.assertRaises(ValidationError):
            validate_editor("javaScript:alert(0)")
        with self.assertRaises(ValidationError):
            validate_editor(" javaScript:alert(0)")


class FullNameCleanTest(SimpleTestCase):
    def test_cleanup(self):
        self.assertEqual("ahoj", clean_fullname("ahoj"))
        self.assertEqual("ahojbar", clean_fullname("ahoj\x00bar"))

    def test_whitespace(self):
        self.assertEqual("ahoj", clean_fullname(" ahoj "))

    def test_none(self):
        self.assertEqual(None, clean_fullname(None))

    def test_invalid(self):
        with self.assertRaises(ValidationError):
            validate_fullname("ahoj\x00bar")

    def test_crud(self):
        with self.assertRaises(ValidationError):
            validate_fullname(".")


class FilenameTest(SimpleTestCase):
    def test_parent(self):
        with self.assertRaises(ValidationError):
            validate_filename("../path")

    def test_absolute(self):
        with self.assertRaises(ValidationError):
            validate_filename("/path")

    def test_good(self):
        validate_filename("path/file")

    def test_simplification(self):
        with self.assertRaises(ValidationError):
            validate_filename("path/./file")

    def test_empty(self):
        validate_filename("")


class RegexTest(SimpleTestCase):
    def test_empty(self):
        with self.assertRaises(ValidationError):
            validate_re("(Min|Short|)$", allow_empty=False)
        validate_re("(Min|Short)$", allow_empty=False)

    def test_syntax(self):
        with self.assertRaises(ValidationError):
            validate_re("(Min|Short")
        validate_re("(Min|Short)")

    def test_groups(self):
        with self.assertRaises(ValidationError):
            validate_re("(Min|Short)", ("component",))
        validate_re("(?P<component>Min|Short)", ("component",))
