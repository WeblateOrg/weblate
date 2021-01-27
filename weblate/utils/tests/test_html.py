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


from django.test import SimpleTestCase

from weblate.utils.html import extract_bleach


class HtmlTestCase(SimpleTestCase):
    def test_noattr(self):
        self.assertEqual(
            extract_bleach("<b>text</b>"), {"tags": {"b"}, "attributes": {"b": set()}}
        )

    def test_attrs(self):
        self.assertEqual(
            extract_bleach('<a href="#">t</a>'),
            {"tags": {"a"}, "attributes": {"a": {"href"}}},
        )

    def test_noclose(self):
        self.assertEqual(
            extract_bleach("<br>"), {"tags": {"br"}, "attributes": {"br": set()}}
        )
