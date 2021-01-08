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
import os

from weblate.fonts.models import FONT_STORAGE, Font
from weblate.trans.tests.test_views import FixtureTestCase

FONT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static",
    "font-droid",
    "DroidSansFallback.ttf",
)


class FontTestCase(FixtureTestCase):
    def add_font(self):
        with open(FONT, "rb") as handle:
            fontfile = FONT_STORAGE.save("DroidSansFallback.ttf", handle)
        return Font.objects.create(font=fontfile, project=self.project, user=self.user)
