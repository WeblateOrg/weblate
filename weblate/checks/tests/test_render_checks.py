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

"""Tests for rendering quality checks."""


from weblate.checks.render import MaxSizeCheck
from weblate.fonts.models import FontGroup, FontOverride
from weblate.fonts.tests.utils import FontTestCase
from weblate.utils.state import STATE_TRANSLATED


class MaxSizeCheckTest(FontTestCase):
    def setUp(self):
        super().setUp()
        self.check = MaxSizeCheck()

    def perform_check(self, target, flags):
        unit = self.get_unit()
        unit.flags = flags
        unit.target = target
        unit.state = STATE_TRANSLATED
        return self.check.check_target(["source"], [target], unit)

    def test_good(self):
        self.assertFalse(self.perform_check("short", "max-size:500"))
        self.assertEqual(self.check.last_font, "sans")

    def test_bad_long(self):
        self.assertTrue(self.perform_check("long" * 50, "max-size:500"))
        self.assertEqual(self.check.last_font, "sans")

    def test_bad_multiline(self):
        self.assertTrue(self.perform_check("long " * 50, "max-size:500"))
        self.assertEqual(self.check.last_font, "sans")

    def test_good_multiline(self):
        self.assertFalse(self.perform_check("long " * 50, "max-size:500:50"))
        self.assertEqual(self.check.last_font, "sans")

    def add_font_group(self):
        font = self.add_font()
        return FontGroup.objects.create(name="droid", font=font, project=self.project)

    def test_custom_font(self):
        self.add_font_group()
        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))
        self.assertEqual(self.check.last_font, "Droid Sans Fallback Regular")

    def test_custom_font_override(self):
        group = self.add_font_group()
        FontOverride.objects.create(
            group=group, language=self.get_translation().language, font=group.font
        )
        self.assertFalse(self.perform_check("short", "max-size:500,font-family:droid"))
        self.assertEqual(self.check.last_font, "Droid Sans Fallback Regular")
