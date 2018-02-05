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

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from six import StringIO

from weblate.trans.tests.test_views import ViewTestCase, FixtureTestCase

from weblate.addons.base import TestAddon
from weblate.addons.cleanup import CleanupAddon
from weblate.addons.example import ExampleAddon
from weblate.addons.flags import SourceEditAddon, TargetEditAddon
from weblate.addons.generate import GenerateFileAddon
from weblate.addons.gettext import (
    GenerateMoAddon, UpdateLinguasAddon, UpdateConfigureAddon, MsgmergeAddon,
)
from weblate.addons.properties import PropertiesSortAddon
from weblate.lang.models import Language
from weblate.trans.models import Unit
from weblate.utils.state import STATE_FUZZY, STATE_EMPTY


class AddonBaseTest(FixtureTestCase):
    def test_is_compatible(self):
        self.assertTrue(TestAddon.is_compatible(self.subproject))

    def test_example(self):
        self.assertTrue(ExampleAddon.is_compatible(self.subproject))
        addon = ExampleAddon.create(self.subproject)
        addon.pre_commit(None)

    def test_create(self):
        addon = TestAddon.create(self.subproject)
        self.assertEqual(addon.name, 'weblate.base.test')
        self.assertEqual(self.subproject.addon_set.count(), 1)

    def test_add_form(self):
        form = TestAddon.get_add_form(self.subproject, data={})
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
        TestAddon.create(self.subproject)
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
        TestAddon.create(self.subproject)
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
        TestAddon.create(self.subproject)
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
        self.assertTrue(
            UpdateLinguasAddon.is_compatible(translation.subproject)
        )
        addon = UpdateLinguasAddon.create(translation.subproject)
        addon.post_add(translation)
        self.assertTrue(
            os.path.exists(translation.addon_commit_files[0])
        )

    def test_update_configure(self):
        translation = self.get_translation()
        self.assertTrue(
            UpdateConfigureAddon.is_compatible(translation.subproject)
        )
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

    def test_generate(self):
        self.edit_unit('Hello, world!\n', 'Nazdar svete!\n')
        self.assertTrue(GenerateFileAddon.is_compatible(self.subproject))
        GenerateFileAddon.create(
            self.subproject,
            configuration={
                'filename': 'stats/{{ language_code }}.json',
                'template': '''{
    "translated": {{ stats.translated_percent }}
}''',
            }
        )
        self.get_translation().commit_pending(None)
        commit = self.subproject.repository.show(
            self.subproject.repository.last_revision
        )
        self.assertIn('stats/cs.json', commit)
        self.assertIn('"translated": 25', commit)


class AndroidAddonTest(ViewTestCase):
    def create_subproject(self):
        return self.create_android(suffix='-not-synced', new_lang='add')

    def test_cleanup(self):
        self.assertTrue(CleanupAddon.is_compatible(self.subproject))
        addon = CleanupAddon.create(self.subproject)
        rev = self.subproject.repository.last_revision
        addon.post_update(self.subproject, '')
        self.assertNotEqual(rev, self.subproject.repository.last_revision)
        commit = self.subproject.repository.show(
            self.subproject.repository.last_revision
        )
        self.assertIn('android-not-synced/values-cs/strings.xml', commit)


class ResxAddonTest(ViewTestCase):
    def create_subproject(self):
        return self.create_resx()

    def test_cleanup(self):
        self.assertTrue(CleanupAddon.is_compatible(self.subproject))
        addon = CleanupAddon.create(self.subproject)
        rev = self.subproject.repository.last_revision
        addon.post_update(
            self.subproject, 'da07dc0dc7052dc44eadfa8f3a2f2609ec634303'
        )
        self.assertNotEqual(rev, self.subproject.repository.last_revision)
        commit = self.subproject.repository.show(
            self.subproject.repository.last_revision
        )
        self.assertIn('resx/cs.resx', commit)


class JsonAddonTest(ViewTestCase):
    def create_subproject(self):
        return self.create_json_mono(suffix='mono-sync')

    def test_cleanup(self):
        self.assertTrue(CleanupAddon.is_compatible(self.subproject))
        addon = CleanupAddon.create(self.subproject)
        rev = self.subproject.repository.last_revision
        addon.post_update(self.subproject, '')
        self.assertNotEqual(rev, self.subproject.repository.last_revision)
        commit = self.subproject.repository.show(
            self.subproject.repository.last_revision
        )
        self.assertIn('json-mono-sync/cs.json', commit)

    def test_unit(self):
        self.assertTrue(SourceEditAddon.is_compatible(self.subproject))
        self.assertTrue(TargetEditAddon.is_compatible(self.subproject))
        SourceEditAddon.create(self.subproject)
        TargetEditAddon.create(self.subproject)
        Unit.objects.all().delete()
        self.subproject.create_translations(force=True)
        self.assertFalse(
            Unit.objects.exclude(
                state__in=(STATE_FUZZY, STATE_EMPTY)
            ).exists()
        )


class ViewTests(ViewTestCase):
    def setUp(self):
        super(ViewTests, self).setUp()
        self.make_manager()

    def test_list(self):
        response = self.client.get(
            reverse('addons', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'Generate mo files')

    def test_add_simple(self):
        response = self.client.post(
            reverse('addons', kwargs=self.kw_subproject),
            {'name': 'weblate.gettext.mo'},
            follow=True
        )
        self.assertContains(response, '1 addon installed')

    def test_add_invalid(self):
        response = self.client.post(
            reverse('addons', kwargs=self.kw_subproject),
            {'name': 'invalid'},
            follow=True
        )
        self.assertContains(response, 'Invalid addon name specified!')

    def test_add_config(self):
        response = self.client.post(
            reverse('addons', kwargs=self.kw_subproject),
            {'name': 'weblate.generate.generate'},
            follow=True
        )
        self.assertContains(response, 'Configure addon')
        response = self.client.post(
            reverse('addons', kwargs=self.kw_subproject),
            {
                'name': 'weblate.generate.generate',
                'form': '1',
                'filename': 'stats/{{ langugage_code }}.json',
                'template': '{"code":"{{ langugage_code }}"}',
            },
            follow=True
        )
        self.assertContains(response, '1 addon installed')

    def test_edit_config(self):
        self.test_add_config()
        addon = self.subproject.addon_set.all()[0]
        response = self.client.get(addon.get_absolute_url())
        self.assertContains(response, 'Configure addon')
        response = self.client.post(addon.get_absolute_url())
        self.assertContains(response, 'Configure addon')
        self.assertContains(response, 'This field is required')

    def test_delete(self):
        addon = SourceEditAddon.create(self.subproject)
        response = self.client.post(
            addon.instance.get_absolute_url(),
            {'delete': '1'},
            follow=True,
        )
        self.assertContains(response, 'no addons currently installed')


class PropertiesAddonTest(ViewTestCase):
    def create_subproject(self):
        return self.create_java()

    def test_sort(self):
        self.edit_unit('Hello, world!\n', 'Nazdar svete!\n')
        self.assertTrue(PropertiesSortAddon.is_compatible(self.subproject))
        PropertiesSortAddon.create(self.subproject)
        self.get_translation().commit_pending(None)
        commit = self.subproject.repository.show(
            self.subproject.repository.last_revision
        )
        self.assertIn('java/swing_messages_cs.properties', commit)


class CommandTest(TestCase):
    """Test for management commands."""
    def test_list_languages(self):
        output = StringIO()
        call_command('list_addons', stdout=output)
        self.assertIn('msgmerge', output.getvalue())
