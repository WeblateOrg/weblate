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

from weblate.fonts.models import FONT_STORAGE
from weblate.fonts.tasks import cleanup_font_files
from weblate.fonts.tests.utils import FontTestCase
from weblate.fonts.utils import configure_fontconfig


class FontModelTest(FontTestCase):
    def test_save(self):
        font = self.add_font()
        self.assertEqual(font.family, "Droid Sans Fallback")
        self.assertEqual(font.style, "Regular")

    def test_cleanup(self):
        configure_fontconfig()
        cleanup_font_files()
        # There should always be fonts.conf present
        self.assertEqual(len(FONT_STORAGE.listdir(".")[1]), 1)
        font = self.add_font()
        self.assertEqual(len(FONT_STORAGE.listdir(".")[1]), 2)
        cleanup_font_files()
        self.assertEqual(len(FONT_STORAGE.listdir(".")[1]), 2)
        font.delete()
        self.assertEqual(len(FONT_STORAGE.listdir(".")[1]), 2)
        cleanup_font_files()
        self.assertEqual(len(FONT_STORAGE.listdir(".")[1]), 1)
