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

import os

from weblate.trans.tests.test_views import ViewTestCase, FixtureTestCase

from weblate.addons.base import TestAddon
from weblate.addons.gettext import GenerateMoAddon
from weblate.addons.models import Addon


class AddonBaseTest(FixtureTestCase):
    def test_is_compatible(self):
        self.assertTrue(TestAddon.is_compatible(self.subproject))

    def test_create(self):
        addon = TestAddon.create(self.subproject)
        self.assertEqual(addon.name, 'weblate.base.test')
        self.assertEqual(self.subproject.addon_set.count(), 1)

    def test_add_form(self):
        form = TestAddon.get_add_form(self.subproject, {})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(self.subproject.addon_set.count(), 1)

        addon = self.subproject.addon_set.all()[0]
        self.assertEqual(addon.name, 'weblate.base.test')


class AddonTest(ViewTestCase):
    def test_gettext_mo(self):
        translation = self.get_translation()
        self.assertTrue(GenerateMoAddon.is_compatible(translation.subproject))
        addon = GenerateMoAddon.create(translation.subproject)
        addon.pre_commit(translation)
        self.assertTrue(
            os.path.exists(translation.addon_commit_files[0])
        )

    def test_registry(self):
        translation = self.get_translation()
        GenerateMoAddon.create(translation.subproject)
        addon = self.subproject.addon_set.all()[0]
        self.assertIsInstance(addon.addon, GenerateMoAddon)
