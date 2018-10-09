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

from unittest import SkipTest
import os

from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from six import StringIO

from weblate.trans.tests.test_views import ViewTestCase, FixtureTestCase

from weblate.addons.base import TestAddon
from weblate.addons.cleanup import CleanupAddon
from weblate.addons.consistency import LangaugeConsistencyAddon
from weblate.addons.discovery import DiscoveryAddon
from weblate.addons.example import ExampleAddon
from weblate.addons.example_pre import ExamplePreAddon
from weblate.addons.flags import (
    SourceEditAddon, TargetEditAddon, SameEditAddon,
)
from weblate.addons.generate import GenerateFileAddon
from weblate.addons.gettext import (
    GenerateMoAddon, UpdateLinguasAddon, UpdateConfigureAddon, MsgmergeAddon,
    GettextCustomizeAddon, GettextAuthorComments,
)
from weblate.addons.json import JSONCustomizeAddon
from weblate.addons.properties import PropertiesSortAddon
from weblate.addons.models import Addon
from weblate.lang.models import Language
from weblate.trans.models import Unit, Translation
from weblate.utils.state import STATE_FUZZY, STATE_EMPTY


class AddonBaseTest(FixtureTestCase):
    def test_can_install(self):
        self.assertTrue(TestAddon.can_install(self.component, None))

    def test_example(self):
        self.assertTrue(ExampleAddon.can_install(self.component, None))
        addon = ExampleAddon.create(self.component)
        addon.pre_commit(None, '')

    def test_create(self):
        addon = TestAddon.create(self.component)
        self.assertEqual(addon.name, 'weblate.base.test')
        self.assertEqual(self.component.addon_set.count(), 1)

    def test_add_form(self):
        form = TestAddon.get_add_form(self.component, data={})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(self.component.addon_set.count(), 1)

        addon = self.component.addon_set.all()[0]
        self.assertEqual(addon.name, 'weblate.base.test')


class IntegrationTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang='add')

    def test_registry(self):
        GenerateMoAddon.create(self.component)
        addon = self.component.addon_set.all()[0]
        self.assertIsInstance(addon.addon, GenerateMoAddon)

    def test_commit(self):
        GenerateMoAddon.create(self.component)
        TestAddon.create(self.component)
        rev = self.component.repository.last_revision
        self.edit_unit('Hello, world!\n', 'Nazdar svete!\n')
        self.get_translation().commit_pending('test', None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn('po/cs.mo', commit)

    def test_add(self):
        UpdateLinguasAddon.create(self.component)
        UpdateConfigureAddon.create(self.component)
        TestAddon.create(self.component)
        rev = self.component.repository.last_revision
        self.component.add_new_language(
            Language.objects.get(code='sk'), None
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn('po/LINGUAS', commit)
        self.assertIn('configure', commit)

    def test_update(self):
        MsgmergeAddon.create(self.component)
        TestAddon.create(self.component)
        rev = self.component.repository.last_revision
        self.component.update_branch()
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn('po/cs.po', commit)

    def test_store(self):
        if not GettextCustomizeAddon.can_install(self.component, None):
            raise SkipTest('po wrap configuration not supported')
        GettextCustomizeAddon.create(
            self.component,
            configuration={'width': -1}
        )
        # Empty addons cache
        self.component.addons_cache = {}
        rev = self.component.repository.last_revision
        self.edit_unit('Hello, world!\n', 'Nazdar svete!\n')
        self.get_translation().commit_pending('test', None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn(
            'Last-Translator: Weblate Test <weblate@example.org>\\nLanguage',
            commit
        )


class GettextAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang='add')

    def test_gettext_mo(self):
        translation = self.get_translation()
        self.assertTrue(
            GenerateMoAddon.can_install(translation.component, None)
        )
        addon = GenerateMoAddon.create(translation.component)
        addon.pre_commit(translation, '')
        self.assertTrue(
            os.path.exists(translation.addon_commit_files[0])
        )

    def test_update_linguas(self):
        translation = self.get_translation()
        self.assertTrue(
            UpdateLinguasAddon.can_install(translation.component, None)
        )
        addon = UpdateLinguasAddon.create(translation.component)
        addon.post_add(translation)
        self.assertTrue(
            os.path.exists(translation.addon_commit_files[0])
        )

    def test_update_configure(self):
        translation = self.get_translation()
        self.assertTrue(
            UpdateConfigureAddon.can_install(translation.component, None)
        )
        addon = UpdateConfigureAddon.create(translation.component)
        addon.post_add(translation)
        self.assertTrue(
            os.path.exists(translation.addon_commit_files[0])
        )

    def test_msgmerge(self):
        self.assertTrue(MsgmergeAddon.can_install(self.component, None))
        addon = MsgmergeAddon.create(self.component)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, '')
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn('po/cs.po', commit)

    def test_generate(self):
        self.edit_unit('Hello, world!\n', 'Nazdar svete!\n')
        self.assertTrue(GenerateFileAddon.can_install(self.component, None))
        GenerateFileAddon.create(
            self.component,
            configuration={
                'filename': 'stats/{{ language_code }}.json',
                'template': '''{
    "translated": {{ stats.translated_percent }}
}''',
            }
        )
        self.get_translation().commit_pending('test', None)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn('stats/cs.json', commit)
        self.assertIn('"translated": 25', commit)

    def test_gettext_comment(self):
        translation = self.get_translation()
        self.assertTrue(
            GettextAuthorComments.can_install(translation.component, None)
        )
        addon = GettextAuthorComments.create(translation.component)
        addon.pre_commit(translation, 'Stojan Jakotyc <stojan@example.com>')
        with open(translation.get_filename(), 'r') as handle:
            content = handle.read()
        self.assertIn('Stojan Jakotyc', content)


class AndroidAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_android(suffix='-not-synced', new_lang='add')

    def test_cleanup(self):
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        addon = CleanupAddon.create(self.component)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, '')
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn('android-not-synced/values-cs/strings.xml', commit)


class ResxAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_resx()

    def test_cleanup(self):
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        addon = CleanupAddon.create(self.component)
        rev = self.component.repository.last_revision
        addon.post_update(
            self.component, 'da07dc0dc7052dc44eadfa8f3a2f2609ec634303'
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn('resx/cs.resx', commit)


class JsonAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_json_mono(suffix='mono-sync')

    def test_cleanup(self):
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        addon = CleanupAddon.create(self.component)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, '')
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn('json-mono-sync/cs.json', commit)

    def test_unit(self):
        self.assertTrue(SourceEditAddon.can_install(self.component, None))
        self.assertTrue(TargetEditAddon.can_install(self.component, None))
        self.assertTrue(SameEditAddon.can_install(self.component, None))
        SourceEditAddon.create(self.component)
        TargetEditAddon.create(self.component)
        SameEditAddon.create(self.component)
        Unit.objects.all().delete()
        self.component.create_translations(force=True)
        self.assertFalse(
            Unit.objects.exclude(
                state__in=(STATE_FUZZY, STATE_EMPTY)
            ).exists()
        )

    def test_customize(self):
        if not JSONCustomizeAddon.can_install(self.component, None):
            raise SkipTest('json dump configuration not supported')
        JSONCustomizeAddon.create(
            self.component,
            configuration={'indent': 8, 'sort': 1}
        )
        # Empty addons cache
        self.component.addons_cache = {}
        rev = self.component.repository.last_revision
        self.edit_unit('Hello, world!\n', 'Nazdar svete!\n')
        self.get_translation().commit_pending('test', None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn(
            '        "try"',
            commit
        )


class ViewTests(ViewTestCase):
    def setUp(self):
        super(ViewTests, self).setUp()
        self.make_manager()

    def test_list(self):
        response = self.client.get(
            reverse('addons', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Generate MO files')

    def test_add_simple(self):
        response = self.client.post(
            reverse('addons', kwargs=self.kw_component),
            {'name': 'weblate.gettext.mo'},
            follow=True
        )
        self.assertContains(response, '1 addon installed')

    def test_add_invalid(self):
        response = self.client.post(
            reverse('addons', kwargs=self.kw_component),
            {'name': 'invalid'},
            follow=True
        )
        self.assertContains(response, 'Invalid addon name specified!')

    def test_add_config(self):
        response = self.client.post(
            reverse('addons', kwargs=self.kw_component),
            {'name': 'weblate.generate.generate'},
            follow=True
        )
        self.assertContains(response, 'Configure addon')
        response = self.client.post(
            reverse('addons', kwargs=self.kw_component),
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
        addon = self.component.addon_set.all()[0]
        response = self.client.get(addon.get_absolute_url())
        self.assertContains(response, 'Configure addon')
        response = self.client.post(addon.get_absolute_url())
        self.assertContains(response, 'Configure addon')
        self.assertContains(response, 'This field is required')

    def test_delete(self):
        addon = SourceEditAddon.create(self.component)
        response = self.client.post(
            addon.instance.get_absolute_url(),
            {'delete': '1'},
            follow=True,
        )
        self.assertContains(response, 'no addons currently installed')


class PropertiesAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_java()

    def test_sort(self):
        self.edit_unit('Hello, world!\n', 'Nazdar svete!\n')
        self.assertTrue(PropertiesSortAddon.can_install(self.component, None))
        PropertiesSortAddon.create(self.component)
        self.get_translation().commit_pending('test', None)
        commit = self.component.repository.show(
            self.component.repository.last_revision
        )
        self.assertIn('java/swing_messages_cs.properties', commit)


class CommandTest(ViewTestCase):
    """Test for management commands."""
    def test_list_languages(self):
        output = StringIO()
        call_command('list_addons', stdout=output)
        self.assertIn('msgmerge', output.getvalue())

    def test_install_not_supported(self):
        output = StringIO()
        call_command(
            'install_addon', '--all',
            '--addon', 'weblate.flags.same_edit',
            stdout=output,
            stderr=output,
        )
        self.assertIn(
            'Can not install on Test/Test',
            output.getvalue()
        )

    def test_install_no_form(self):
        output = StringIO()
        call_command(
            'install_addon', '--all',
            '--addon', 'weblate.gettext.mo',
            stdout=output,
            stderr=output,
        )
        self.assertIn(
            'Successfully installed on Test/Test',
            output.getvalue()
        )

    def test_install_form(self):
        output = StringIO()
        call_command(
            'install_addon', '--all',
            '--addon', 'weblate.gettext.customize',
            '--configuration', '{"width":77}',
            stdout=output,
            stderr=output,
        )
        self.assertIn(
            'Successfully installed on Test/Test',
            output.getvalue()
        )
        addon = Addon.objects.get(component=self.component)
        self.assertEqual(addon.configuration, {'width': 77})
        output = StringIO()
        call_command(
            'install_addon', '--all',
            '--addon', 'weblate.gettext.customize',
            '--configuration', '{"width":-1}',
            stdout=output,
            stderr=output,
        )
        self.assertIn(
            'Already installed on Test/Test',
            output.getvalue()
        )
        addon = Addon.objects.get(component=self.component)
        self.assertEqual(addon.configuration, {'width': 77})
        output = StringIO()
        call_command(
            'install_addon', '--all', '--update',
            '--addon', 'weblate.gettext.customize',
            '--configuration', '{"width":-1}',
            stdout=output,
            stderr=output,
        )
        self.assertIn(
            'Successfully updated on Test/Test',
            output.getvalue()
        )
        addon = Addon.objects.get(component=self.component)
        self.assertEqual(addon.configuration, {'width': -1})

    def test_install_addon_wrong(self):
        output = StringIO()
        self.assertRaises(
            CommandError,
            call_command,
            'install_addon', '--all',
            '--addon', 'weblate.gettext.nonexisting',
            '--configuration', '{"width":77}',
        )
        self.assertRaises(
            CommandError,
            call_command,
            'install_addon', '--all',
            '--addon', 'weblate.gettext.customize',
            '--configuration', '{',
        )
        self.assertRaises(
            CommandError,
            call_command,
            'install_addon', '--all',
            '--addon', 'weblate.gettext.customize',
            '--configuration', '{}',
            stdout=output,
        )
        self.assertRaises(
            CommandError,
            call_command,
            'install_addon', '--all',
            '--addon', 'weblate.gettext.customize',
            '--configuration', '{"width":-65535}',
            stderr=output,
        )


class DiscoveryTest(ViewTestCase):
    def test_creation(self):
        addon = DiscoveryAddon.create(
            self.component,
            configuration={
                'file_format': 'po',
                'match': r'(?P<component>[^/]*)/(?P<language>[^/]*)\.po',
                'name_template': '{{ component|title }}',
                'language_regex': '^(?!xx).*$',
                'base_file_template': '',
                'remove': True,
            },
        )
        self.assertEqual(self.component.get_linked_childs().count(), 0)
        addon.perform()
        self.assertEqual(self.component.get_linked_childs().count(), 3)

    def test_form(self):
        self.user.is_superuser = True
        self.user.save()
        # Missing params
        response = self.client.post(
            reverse('addons', kwargs=self.kw_component),
            {
                'name': 'weblate.discovery.discovery',
                'form': '1',
            },
            follow=True
        )
        self.assertNotContains(response, 'Please review and confirm')
        # Correct params for confirmation
        response = self.client.post(
            reverse('addons', kwargs=self.kw_component),
            {
                'name': 'weblate.discovery.discovery',
                'form': '1',
                'file_format': 'auto',
                'match': r'(?P<component>[^/]*)/(?P<language>[^/]*)\.po',
                'name_template': '{{ component|title }}',
                'language_regex': '^(?!xx).*$',
                'base_file_template': '',
                'remove': True,
            },
            follow=True
        )
        self.assertContains(response, 'Please review and confirm')
        # Confirmation
        response = self.client.post(
            reverse('addons', kwargs=self.kw_component),
            {
                'name': 'weblate.discovery.discovery',
                'form': '1',
                'match': r'(?P<component>[^/]*)/(?P<language>[^/]*)\.po',
                'file_format': 'auto',
                'name_template': '{{ component|title }}',
                'language_regex': '^(?!xx).*$',
                'base_file_template': '',
                'remove': True,
                'confirm': True,
            },
            follow=True
        )
        self.assertContains(response, '1 addon installed')


class ScriptsTest(ViewTestCase):
    def test_example_pre(self):
        self.assertTrue(ExamplePreAddon.can_install(self.component, None))
        translation = self.get_translation()
        addon = ExamplePreAddon.create(self.component)
        addon.pre_commit(translation, '')
        self.assertIn(
            os.path.join(
                self.component.full_path,
                'po/{}.po'.format(translation.language_code)
            ),
            translation.addon_commit_files
        )


class LanguageConsistencyTest(ViewTestCase):
    def test_language_consistency(self):
        self.component.new_lang = 'add'
        self.component.new_base = 'po/hello.pot'
        self.component.save()
        self.create_ts(
            name='TS',
            new_lang='add',
            new_base='ts/cs.ts',
            project=self.component.project,
        )
        self.assertEqual(Translation.objects.count(), 4)

        # Installation should make languages consistent
        addon = LangaugeConsistencyAddon.create(self.component)
        self.assertEqual(Translation.objects.count(), 6)

        # Add one language
        language = Language.objects.get(code='af')
        self.component.add_new_language(language, None)
        self.assertEqual(
            Translation.objects.filter(
                language=language,
                component__project=self.component.project
            ).count(),
            2
        )

        # Trigger post update signal, should do nothing
        addon.post_update(self.component, '')
        self.assertEqual(Translation.objects.count(), 8)
