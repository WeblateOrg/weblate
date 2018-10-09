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

"""Test for translation models."""

import os
import shutil

from django.core.exceptions import ValidationError

from weblate.checks.models import Check
from weblate.formats import ParseError
from weblate.trans.models import (
    Project, Component, Unit, Suggestion,
)
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_TRANSLATED


class ComponentTest(RepoTestCase):
    """Component object testing."""
    def verify_component(self, component, translations, lang=None, units=0,
                         unit='Hello, world!\n', fail=False):
        # Validation
        if fail:
            self.assertRaises(
                ValidationError,
                component.full_clean
            )
        else:
            component.full_clean()
        # Correct path
        self.assertTrue(os.path.exists(component.full_path))
        # Count translations
        self.assertEqual(
            component.translation_set.count(), translations
        )
        if lang is not None:
            # Grab translation
            translation = component.translation_set.get(language_code=lang)
            # Count units in it
            self.assertEqual(translation.unit_set.count(), units)
            # Check whether unit exists
            self.assertTrue(translation.unit_set.filter(source=unit).exists())

        if component.has_template() and component.edit_template:
            translation = component.translation_set.get(
                filename=component.template
            )
            # Count units in it
            self.assertEqual(translation.unit_set.count(), units)
            # Count translated units in it
            self.assertEqual(
                translation.unit_set.filter(
                    state__gte=STATE_TRANSLATED
                ).count(),
                units
            )

    def test_create(self):
        component = self.create_component()
        self.verify_component(component, 3, 'cs', 4)
        self.assertTrue(os.path.exists(component.full_path))

    def test_create_dot(self):
        component = self._create_component(
            'auto',
            './po/*.po',
        )
        self.verify_component(component, 3, 'cs', 4)
        self.assertTrue(os.path.exists(component.full_path))
        self.assertEqual('po/*.po', component.filemask)

    def test_create_iphone(self):
        component = self.create_iphone()
        self.verify_component(component, 1, 'cs', 4)

    def test_create_ts(self):
        component = self.create_ts('-translated')
        self.verify_component(component, 1, 'cs', 4)

        unit = Unit.objects.get(source__startswith='Orangutan')
        self.assertTrue(unit.is_plural())
        self.assertFalse(unit.translated)
        self.assertFalse(unit.fuzzy)

        unit = Unit.objects.get(source__startswith='Hello')
        self.assertFalse(unit.is_plural())
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(unit.target, 'Hello, world!\n')

        unit = Unit.objects.get(source__startswith='Thank ')
        self.assertFalse(unit.is_plural())
        self.assertFalse(unit.translated)
        self.assertTrue(unit.fuzzy)
        self.assertEqual(unit.target, 'Thanks')

    def test_create_ts_mono(self):
        component = self.create_ts_mono()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_po_pot(self):
        component = self._create_component(
            'po',
            'po/*.po',
            new_base='po/project.pot'
        )
        self.verify_component(component, 3, 'cs', 4, fail=True)

    def test_create_filtered(self):
        component = self._create_component(
            'po',
            'po/*.po',
            language_regex='^cs$',
        )
        self.verify_component(component, 1, 'cs', 4)

    def test_create_auto_pot(self):
        component = self._create_component(
            'auto',
            'po/*.po',
            new_base='po/project.pot'
        )
        self.verify_component(component, 3, 'cs', 4, fail=True)

    def test_create_po(self):
        component = self.create_po()
        self.verify_component(component, 3, 'cs', 4)

    def test_create_po_mercurial(self):
        component = self.create_po_mercurial()
        self.verify_component(component, 3, 'cs', 4)

    def test_create_po_branch(self):
        component = self.create_po_branch()
        self.verify_component(component, 3, 'cs', 4)

    def test_create_po_push(self):
        component = self.create_po_push()
        self.verify_component(component, 3, 'cs', 4)

    def test_create_po_svn(self):
        component = self.create_po_svn()
        self.verify_component(component, 3, 'cs', 4)

    def test_create_po_empty(self):
        component = self.create_po_empty()
        self.verify_component(component, 0)

    def test_create_po_link(self):
        component = self.create_po_link()
        self.verify_component(component, 4, 'cs', 4)

    def test_create_po_mono(self):
        component = self.create_po_mono()
        self.verify_component(component, 4, 'cs', 4)

    def test_create_android(self):
        component = self.create_android()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_json(self):
        component = self.create_json()
        self.verify_component(component, 1, 'cs', 4)

    def test_create_json_mono(self):
        component = self.create_json_mono()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_json_nested(self):
        component = self.create_json_mono(suffix='nested')
        self.verify_component(component, 2, 'cs', 4)

    def test_create_json_webextension(self):
        component = self.create_json_webextension()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_joomla(self):
        component = self.create_joomla()
        self.verify_component(component, 3, 'cs', 4)

    def test_create_tsv_simple(self):
        component = self._create_component(
            'csv-simple',
            'tsv/*.txt',
        )
        self.verify_component(component, 1, 'cs', 4, 'Hello, world!')

    def test_create_tsv_simple_iso(self):
        component = self._create_component(
            'csv-simple-iso',
            'tsv/*.txt',
        )
        self.verify_component(component, 1, 'cs', 4, 'Hello, world!')

    def test_create_csv(self):
        component = self.create_csv()
        self.verify_component(component, 1, 'cs', 4)

    def test_create_csv_mono(self):
        component = self.create_csv_mono()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_php_mono(self):
        component = self.create_php_mono()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_tsv(self):
        component = self.create_tsv()
        self.verify_component(component, 1, 'cs', 4, 'Hello, world!')

    def test_create_java(self):
        component = self.create_java()
        self.verify_component(component, 3, 'cs', 4)

    def test_create_xliff(self):
        component = self.create_xliff()
        self.verify_component(component, 1, 'cs', 4)

    def test_create_xliff_complex(self):
        component = self.create_xliff('complex')
        self.verify_component(component, 1, 'cs', 4)

    def test_create_xliff_mono(self):
        component = self.create_xliff_mono()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_xliff_dph(self):
        component = self.create_xliff('DPH')
        self.verify_component(component, 1, 'en', 9, 'DPH')

    def test_create_xliff_empty(self):
        component = self.create_xliff('EMPTY')
        self.verify_component(component, 1, 'en', 6, 'DPH')

    def test_create_xliff_resname(self):
        component = self.create_xliff('Resname')
        self.verify_component(component, 1, 'en', 2, 'Hi')

    def test_create_resx(self):
        component = self.create_resx()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_yaml(self):
        component = self.create_yaml()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_ruby_yaml(self):
        component = self.create_ruby_yaml()
        self.verify_component(component, 2, 'cs', 4)

    def test_create_dtd(self):
        component = self.create_dtd()
        self.verify_component(component, 2, 'cs', 4)

    def test_link(self):
        component = self.create_link()
        self.verify_component(component, 3, 'cs', 4)

    def test_check_flags(self):
        """Check flags validation."""
        component = self.create_component()
        component.full_clean()

        component.check_flags = 'ignore-inconsistent'
        component.full_clean()

        component.check_flags = 'rst-text,ignore-inconsistent'
        component.full_clean()

        component.check_flags = 'nonsense'
        self.assertRaisesMessage(
            ValidationError,
            'Invalid check flag: "nonsense"',
            component.full_clean
        )

        component.check_flags = 'rst-text,ignore-nonsense'
        self.assertRaisesMessage(
            ValidationError,
            'Invalid check flag: "ignore-nonsense"',
            component.full_clean
        )

    def test_lang_code_template(self):
        component = Component(project=Project())
        component.filemask = 'Solution/Project/Resources.*.resx'
        component.template = 'Solution/Project/Resources.resx'
        self.assertEqual(
            component.get_lang_code('Solution/Project/Resources.resx'),
            'en'
        )

    def test_switch_branch(self):
        component = self.create_po()
        # Switch to translation branch
        self.verify_component(component, 3, 'cs', 4)
        component.branch = 'translations'
        component.filemask = 'translations/*.po'
        component.clean()
        component.save()
        self.verify_component(component, 3, 'cs', 4)
        # Switch back to master branch
        component.branch = 'master'
        component.filemask = 'po/*.po'
        component.clean()
        component.save()
        self.verify_component(component, 3, 'cs', 4)

    def test_update_checks(self):
        """Setting of check_flags changes checks for related units."""
        component = self.create_component()
        self.assertEqual(Check.objects.count(), 3)
        check = Check.objects.all()[0]
        component.check_flags = 'ignore-{0}'.format(check.check)
        component.save()
        self.assertEqual(Check.objects.count(), 0)


class ComponentDeleteTest(RepoTestCase):
    """Component object deleting testing."""
    def test_delete(self):
        component = self.create_component()
        self.assertTrue(os.path.exists(component.full_path))
        component.delete()
        self.assertFalse(os.path.exists(component.full_path))
        self.assertEqual(0, Component.objects.count())

    def test_delete_link(self):
        component = self.create_link()
        main_project = Component.objects.get(slug='test')
        self.assertTrue(os.path.exists(main_project.full_path))
        component.delete()
        self.assertTrue(os.path.exists(main_project.full_path))

    def test_delete_all(self):
        component = self.create_component()
        self.assertTrue(os.path.exists(component.full_path))
        Component.objects.all().delete()
        self.assertFalse(os.path.exists(component.full_path))


class ComponentChangeTest(RepoTestCase):
    """Component object change testing."""
    def test_rename(self):
        link_component = self.create_link()
        component = link_component.linked_component
        self.assertTrue(
            Component.objects.filter(repo='weblate://test/test').exists()
        )

        old_path = component.full_path
        self.assertTrue(os.path.exists(old_path))
        component.slug = 'changed'
        component.save()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(component.full_path))

        self.assertTrue(
            Component.objects.filter(repo='weblate://test/changed').exists()
        )
        self.assertFalse(
            Component.objects.filter(repo='weblate://test/test').exists()
        )

    def test_change_project(self):
        component = self.create_component()

        # Create and verify suggestion
        Suggestion.objects.create(
            project=component.project,
            content_hash=1,
            language=component.translation_set.all()[0].language,
        )
        self.assertEqual(component.project.suggestion_set.count(), 1)

        # Check current path exists
        old_path = component.full_path
        self.assertTrue(os.path.exists(old_path))

        # Crete target project
        second = Project.objects.create(
            name='Test2',
            slug='test2',
            web='https://weblate.org/'
        )

        # Move component
        component.project = second
        component.save()

        # Check new path exists
        new_path = component.full_path
        self.assertTrue(os.path.exists(new_path))

        # Check paths differ
        self.assertNotEqual(old_path, new_path)

        # Check suggestion has been copied
        self.assertEqual(component.project.suggestion_set.count(), 1)

    def test_change_to_mono(self):
        """Test swtiching to monolingual format on the fly."""
        component = self._create_component(
            'po',
            'po-mono/*.po',
        )
        self.assertEqual(component.translation_set.count(), 4)
        component.file_format = 'po-mono'
        component.template = 'po-mono/en.po'
        component.save()
        self.assertEqual(component.translation_set.count(), 4)


class ComponentValidationTest(RepoTestCase):
    """Component object validation testing."""
    def setUp(self):
        super(ComponentValidationTest, self).setUp()
        self.component = self.create_component()
        # Ensure we have correct component
        self.component.full_clean()

    def test_commit_message(self):
        """Invalid commit message"""
        self.component.commit_message = '{% if %}'
        self.assertRaises(
            ValidationError,
            self.component.full_clean
        )

    def test_filemask(self):
        """Invalid mask"""
        self.component.filemask = 'foo/x.po'
        self.assertRaisesMessage(
            ValidationError,
            'File mask does not contain * as a language placeholder!',
            self.component.full_clean
        )

    def test_no_matches(self):
        """Not matching mask"""
        self.component.filemask = 'foo/*.po'
        self.assertRaisesMessage(
            ValidationError,
            'The mask did not match any files!',
            self.component.full_clean
        )

    def test_fileformat(self):
        """Unknown file format"""
        self.component.filemask = 'invalid/*.invalid'
        self.assertRaisesMessage(
            ValidationError,
            'Format of 2 matched files could not be recognized.',
            self.component.full_clean
        )

    def test_repoweb(self):
        """Invalid repoweb format"""
        self.component.repoweb = 'http://%(foo)s/%(bar)s/%72'
        self.assertRaisesMessage(
            ValidationError,
            "Bad format string ('foo')",
            self.component.full_clean
        )
        self.component.repoweb = ''

    def test_link_incomplete(self):
        """Incomplete link"""
        self.component.repo = 'weblate://foo'
        self.component.push = ''
        self.assertRaisesMessage(
            ValidationError,
            'Invalid link to a Weblate project, '
            'use weblate://project/component.',
            self.component.full_clean
        )

    def test_link_nonexisting(self):
        """Link to non existing project"""
        self.component.repo = 'weblate://foo/bar'
        self.component.push = ''
        self.assertRaisesMessage(
            ValidationError,
            'Invalid link to a Weblate project, '
            'use weblate://project/component.',
            self.component.full_clean
        )

    def test_link_self(self):
        """Link pointing to self"""
        self.component.repo = 'weblate://test/test'
        self.component.push = ''
        self.assertRaisesMessage(
            ValidationError,
            'Invalid link to a Weblate project, '
            'can not link to self!',
            self.component.full_clean
        )

    def test_validation_mono(self):
        self.component.project.delete()
        project = self.create_po_mono()
        # Correct project
        project.full_clean()
        # Not existing file
        project.template = 'not-existing'
        self.assertRaisesMessage(
            ValidationError,
            'Template file not found!',
            project.full_clean
        )

    def test_validation_languge_re(self):
        self.component.language_regex = '[-'
        self.assertRaises(
            ValidationError,
            self.component.full_clean
        )

    def test_validation_newlang(self):
        self.component.new_base = 'po/project.pot'
        self.component.save()

        # Check that it warns about unused pot
        self.assertRaisesMessage(
            ValidationError,
            'Base file for new translations is not used '
            'because of component settings.',
            self.component.full_clean
        )

        self.component.new_lang = 'add'
        self.component.save()

        # Check that it doesn't warn about not supported format
        self.component.full_clean()

        self.component.file_format = 'po'
        self.component.save()

        # Clean class cache, pylint: disable=protected-access
        del self.component.__dict__['file_format']

        # With correct format it should validate
        self.component.full_clean()

    def test_lang_code(self):
        component = Component()
        component.filemask = 'Solution/Project/Resources.*.resx'
        self.assertEqual(
            component.get_lang_code('Solution/Project/Resources.es-mx.resx'),
            'es-mx'
        )
        self.assertEqual(
            component.get_lang_code('Solution/Project/Resources.resx'),
            ''
        )
        self.assertRaisesMessage(
            ValidationError,
            'Got empty language code for '
            'Solution/Project/Resources.resx, please check filemask!',
            component.clean_lang_codes,
            [
                'Solution/Project/Resources.resx',
                'Solution/Project/Resources.de.resx',
                'Solution/Project/Resources.es.resx',
                'Solution/Project/Resources.es-mx.resx',
                'Solution/Project/Resources.fr.resx',
                'Solution/Project/Resources.fr-fr.resx',
            ]
        )

    def test_lang_code_double(self):
        component = Component()
        component.filemask = 'path/*/resources/MessagesBundle_*.properties'
        self.assertEqual(
            component.get_lang_code(
                'path/pt/resources/MessagesBundle_pt_BR.properties'
            ),
            'pt_BR'
        )
        self.assertEqual(
            component.get_lang_code(
                'path/el/resources/MessagesBundle_el.properties'
            ),
            'el'
        )


class ComponentErrorTest(RepoTestCase):
    """Test for error handling"""

    def setUp(self):
        super(ComponentErrorTest, self).setUp()
        self.component = self.create_ts_mono()
        # Change to invalid pull/push URL
        repository = self.component.repository
        with repository.lock:
            repository.configure_remote(
                'file:/dev/null',
                'file:/dev/null',
                'master'
            )

    def test_failed_update(self):
        self.assertFalse(
            self.component.do_update()
        )

    def test_failed_update_remote(self):
        self.assertFalse(
            self.component.update_remote_branch()
        )

    def test_failed_push(self):
        testfile = os.path.join(self.component.full_path, 'README.md')
        with open(testfile, 'a') as handle:
            handle.write('CHANGE')
        with self.component.repository.lock:
            self.component.repository.commit('test', files=['README.md'])
        self.assertFalse(
            self.component.do_push(None)
        )

    def test_failed_reset(self):
        # Corrupt Git database so that reset fails
        shutil.rmtree(
            os.path.join(self.component.full_path, '.git', 'objects', 'pack')
        )
        self.assertFalse(
            self.component.do_reset(None)
        )

    def test_invalid_templatename(self):
        self.component.template = 'foo.bar'
        # Clean class cache, pylint: disable=protected-access
        del self.component.__dict__['template_store']

        self.assertRaises(
            ParseError,
            lambda: self.component.template_store
        )
        self.assertRaises(
            ValidationError,
            self.component.clean
        )

    def test_invalid_filename(self):
        translation = self.component.translation_set.get(language_code='cs')
        translation.filename = 'foo.bar'
        self.assertRaises(
            ParseError,
            lambda: translation.store
        )
        self.assertRaises(
            ValidationError,
            translation.clean
        )

    def test_invalid_storage(self):
        testfile = os.path.join(self.component.full_path, 'ts-mono', 'cs.ts')
        with open(testfile, 'a') as handle:
            handle.write('CHANGE')
        translation = self.component.translation_set.get(language_code='cs')
        self.assertRaises(
            ParseError,
            lambda: translation.store
        )
        self.assertRaises(
            ValidationError,
            translation.clean
        )

    def test_invalid_template_storage(self):
        testfile = os.path.join(self.component.full_path, 'ts-mono', 'en.ts')
        with open(testfile, 'a') as handle:
            handle.write('CHANGE')

        # Clean class cache, pylint: disable=protected-access
        del self.component.__dict__['template_store']

        self.assertRaises(
            ParseError,
            lambda: self.component.template_store
        )
        self.assertRaises(
            ValidationError,
            self.component.clean
        )


class ComponentEditTest(ViewTestCase):
    """Test for error handling"""
    @staticmethod
    def remove_units(store):
        store.units = []
        store.save()

    def test_unit_disappear(self):
        translation = self.component.translation_set.get(language_code='cs')

        if self.component.has_template():
            self.remove_units(self.component.template_store.store)
        self.remove_units(translation.store.store)

        # Clean class cache, pylint: disable=protected-access
        del self.component.__dict__['template_store']
        del translation.__dict__['store']

        unit = translation.unit_set.all()[0]
        request = self.get_request('/')

        self.assertTrue(
            unit.translate(request, ['Empty'], STATE_TRANSLATED)
        )


class ComponentEditMonoTest(ComponentEditTest):
    """Test for error handling"""
    def create_component(self):
        return self.create_ts_mono()

    @staticmethod
    def remove_units(store):
        store.parse(store.XMLskeleton.replace("\n", "").encode('utf-8'))
        store.save()

    def test_unit_add(self):
        translation = self.component.translation_set.get(language_code='cs')

        self.remove_units(translation.store.store)

        # Clean class cache, pylint: disable=protected-access
        del translation.__dict__['store']

        unit = translation.unit_set.all()[0]
        request = self.get_request('/')

        self.assertTrue(
            unit.translate(request, ['Empty'], STATE_TRANSLATED)
        )
