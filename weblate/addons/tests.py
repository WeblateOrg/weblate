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
from weblate.addons.gettext import (
    GenerateMoAddon, UpdateLinguasAddon, UpdateConfigureAddon, MsgmergeAddon,
)
from weblate.addons.models import Addon
from weblate.lang.models import Language


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


class IntegrationTest(ViewTestCase):
    def create_subproject(self):
        return self.create_po_new_base(new_lang='add')

    def test_registry(self):
        GenerateMoAddon.create(self.subproject)
        addon = self.subproject.addon_set.all()[0]
        self.assertIsInstance(addon.addon, GenerateMoAddon)

    def test_commit(self):
        GenerateMoAddon.create(self.subproject)
        rev = self.subproject.repository.last_revision
        self.edit_unit('Hello, world!\n', 'Nazdar svete!\n')
        self.get_translation().commit_pending(None)
        self.assertNotEqual(rev, self.subproject.repository.last_revision)
        commit = self.subproject.repository.show(
            self.subproject.repository.last_revision
        )
        self.assertIn('po/cs.mo', commit)

    def test_add(self):
        UpdateLinguasAddon.create(self.subproject)
        UpdateConfigureAddon.create(self.subproject)
        rev = self.subproject.repository.last_revision
        self.subproject.add_new_language(
            Language.objects.get(code='sk'), None
        )
        self.assertNotEqual(rev, self.subproject.repository.last_revision)
        commit = self.subproject.repository.show(
            self.subproject.repository.last_revision
        )
        self.assertIn('po/LINGUAS', commit)
        self.assertIn('configure', commit)

    def test_update(self):
        MsgmergeAddon.create(self.subproject)
        rev = self.subproject.repository.last_revision
        self.subproject.update_branch()
        self.assertNotEqual(rev, self.subproject.repository.last_revision)
        commit = self.subproject.repository.show(
            self.subproject.repository.last_revision
        )
        self.assertIn('po/cs.po', commit)


class GettextAddonTest(ViewTestCase):
    def create_subproject(self):
        return self.create_po_new_base(new_lang='add')

    def test_gettext_mo(self):
        translation = self.get_translation()
        self.assertTrue(GenerateMoAddon.is_compatible(translation.subproject))
        addon = GenerateMoAddon.create(translation.subproject)
        addon.pre_commit(translation)
        self.assertTrue(
            os.path.exists(translation.addon_commit_files[0])
        )

    def test_update_linguas(self):
        translation = self.get_translation()
        self.assertTrue(UpdateLinguasAddon.is_compatible(translation.subproject))
        addon = UpdateLinguasAddon.create(translation.subproject)
        addon.post_add(translation)
        self.assertTrue(
            os.path.exists(translation.addon_commit_files[0])
        )

    def test_update_configure(self):
        translation = self.get_translation()
        self.assertTrue(UpdateConfigureAddon.is_compatible(translation.subproject))
        addon = UpdateConfigureAddon.create(translation.subproject)
        addon.post_add(translation)
        self.assertTrue(
            os.path.exists(translation.addon_commit_files[0])
        )

    def test_msgmerge(self):
        self.assertTrue(MsgmergeAddon.is_compatible(self.subproject))
        addon = MsgmergeAddon.create(self.subproject)
        rev = self.subproject.repository.last_revision
        addon.post_update(self.subproject, '')
        self.assertNotEqual(rev, self.subproject.repository.last_revision)
        commit = self.subproject.repository.show(
            self.subproject.repository.last_revision
        )
        self.assertIn('po/cs.po', commit)
