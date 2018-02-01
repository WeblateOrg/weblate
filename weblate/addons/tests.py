# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from weblate.trans.tests.test_views import FixtureTestCase

from weblate.addons.base import TestAddon
from weblate.addons.models import Addon


class AddonTest(FixtureTestCase):
    def test_add(self):
        form = TestAddon.get_add_form(self.subproject, {})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(self.subproject.addon_set.count(), 1)

        addon = self.subproject.addon_set.all()[0]
        self.assertEqual(addon.name, 'weblate.base.test')
