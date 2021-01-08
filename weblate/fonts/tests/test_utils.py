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

"""Test for fonts."""

from django.test import SimpleTestCase

from weblate.fonts.utils import check_render_size, get_font_weight


class RenderTest(SimpleTestCase):
    def test_render(self):
        self.assertTrue(
            check_render_size("sans", get_font_weight("normal"), 12, 0, "ahoj", 100, 1)
        )
        self.assertFalse(
            check_render_size("sans", get_font_weight("normal"), 12, 0, "ahoj", 10, 1)
        )
