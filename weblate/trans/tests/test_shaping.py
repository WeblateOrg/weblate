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

"""Test for shapings."""


from weblate.trans.models import Shaping
from weblate.trans.tests.test_views import ViewTestCase


class ShapingTest(ViewTestCase):
    def create_component(self):
        return self.create_android()

    def add_shapings(self):
        request = self.get_request()
        translation = self.component.source_translation
        translation.new_unit(request, "bar", "Default string")
        translation.new_unit(request, "barMin", "Min string")
        translation.new_unit(request, "barShort", "Short string")

    def test_edit_component(self):
        self.add_shapings()
        self.assertEqual(Shaping.objects.count(), 0)
        self.component.shaping_regex = "(Min|Short)$"
        self.component.save()
        self.assertEqual(Shaping.objects.count(), 1)
        self.component.shaping_regex = ""
        self.component.save()
        self.assertEqual(Shaping.objects.count(), 0)

    def test_add_units(self):
        self.component.shaping_regex = "(Min|Short)$"
        self.component.save()
        self.assertEqual(Shaping.objects.count(), 0)
        self.add_shapings()
        self.assertEqual(Shaping.objects.count(), 1)
