# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
Tests for translation models.
"""

import os
import shutil

from django.core.exceptions import ValidationError

from weblate.trans.formats import ParseError
from weblate.trans.models import (
    Project, SubProject, Unit, Suggestion, IndexUpdate,
)
from weblate.trans.tests import OverrideSettings
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.test_views import ViewTestCase


class SubProjectTest(RepoTestCase):
    """
    SubProject object testing.
    """
    def verify_subproject(self, project, translations, lang=None, units=0,
                          unit='Hello, world!\n', fail=False):
        # Validation
        if fail:
            self.assertRaises(
                ValidationError,
                project.full_clean
            )
        else:
            project.full_clean()
        # Correct path
        self.assertTrue(os.path.exists(project.get_path()))
        # Count translations
        self.assertEqual(
            project.translation_set.count(), translations
        )
        if lang is not None:
            # Grab translation
            translation = project.translation_set.get(language_code=lang)
            # Count units in it
            self.assertEqual(translation.unit_set.count(), units)
            # Check whether unit exists
            self.assertTrue(translation.unit_set.filter(source=unit).exists())

    def test_create(self):
        project = self.create_subproject()
        self.verify_subproject(project, 3, 'cs', 4)
        self.assertTrue(os.path.exists(project.get_path()))

    def test_create_dot(self):
        project = self._create_subproject(
            'auto',
            './po/*.po',
        )
        self.verify_subproject(project, 3, 'cs', 4)
        self.assertTrue(os.path.exists(project.get_path()))
        self.assertEqual('po/*.po', project.filemask)

    def test_create_iphone(self):
        project = self.create_iphone()
        self.verify_subproject(project, 1, 'cs', 4)

    def test_create_ts(self):
        project = self.create_ts('-translated')
        self.verify_subproject(project, 1, 'cs', 4)

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
        project = self.create_ts_mono()
        self.verify_subproject(project, 2, 'cs', 4)

    def test_create_po_pot(self):
        project = self._create_subproject(
            'po',
            'po/*.po',
            'po/project.pot'
        )
        self.verify_subproject(project, 3, 'cs', 4, fail=True)

    def test_create_filtered(self):
        project = self._create_subproject(
            'po',
            'po/*.po',
            language_regex='^cs$',
        )
        self.verify_subproject(project, 1, 'cs', 4)

    def test_create_auto_pot(self):
        project = self._create_subproject(
            'auto',
            'po/*.po',
            'po/project.pot'
        )
        self.verify_subproject(project, 3, 'cs', 4, fail=True)

    def test_create_po(self):
        project = self.create_po()
        self.verify_subproject(project, 3, 'cs', 4)

    def test_create_po_mercurial(self):
        project = self.create_po_mercurial()
        self.verify_subproject(project, 3, 'cs', 4)

    def test_create_po_empty(self):
        project = self.create_po_empty()
        self.verify_subproject(project, 0)

    def test_create_po_link(self):
        project = self.create_po_link()
        self.verify_subproject(project, 4, 'cs', 4)

    def test_create_po_mono(self):
        project = self.create_po_mono()
        self.verify_subproject(project, 4, 'cs', 4)

    def test_create_android(self):
        project = self.create_android()
        self.verify_subproject(project, 2, 'cs', 4)

    def test_create_json(self):
        project = self.create_json()
        self.verify_subproject(project, 1, 'cs', 4)

    def test_create_json_mono(self):
        project = self.create_json_mono()
        self.verify_subproject(project, 2, 'cs', 4)

    def test_create_tsv_simple(self):
        project = self._create_subproject(
            'csv-simple',
            'tsv/*.txt',
        )
        self.verify_subproject(project, 1, 'cs', 4, 'Hello, world!')

    def test_create_tsv_simple_iso(self):
        project = self._create_subproject(
            'csv-simple-iso',
            'tsv/*.txt',
        )
        self.verify_subproject(project, 1, 'cs', 4, 'Hello, world!')

    def test_create_csv(self):
        project = self.create_csv()
        self.verify_subproject(project, 1, 'cs', 4)

    def test_create_csv_mono(self):
        project = self.create_csv_mono()
        self.verify_subproject(project, 2, 'cs', 4)

    def test_create_php_mono(self):
        project = self.create_php_mono()
        self.verify_subproject(project, 2, 'cs', 4)

    def test_create_tsv(self):
        project = self.create_tsv()
        self.verify_subproject(project, 1, 'cs', 4, 'Hello, world!')

    def test_create_java(self):
        project = self.create_java()
        self.verify_subproject(project, 3, 'cs', 4)

    def test_create_xliff(self):
        project = self.create_xliff()
        self.verify_subproject(project, 1, 'cs', 4)

    def test_create_xliff_complex(self):
        project = self.create_xliff('complex')
        self.verify_subproject(project, 1, 'cs', 4)

    def test_create_xliff_mono(self):
        project = self.create_xliff_mono()
        self.verify_subproject(project, 2, 'cs', 4)

    def test_create_xliff_dph(self):
        project = self.create_xliff('DPH')
        self.verify_subproject(project, 1, 'en', 9, 'DPH')

    def test_create_xliff_empty(self):
        project = self.create_xliff('EMPTY')
        self.verify_subproject(project, 1, 'en', 6, 'DPH')

    def test_create_xliff_resname(self):
        project = self.create_xliff('Resname')
        self.verify_subproject(project, 1, 'en', 2, 'Hi')

    def test_create_resx(self):
        project = self.create_resx()
        self.verify_subproject(project, 2, 'cs', 4)

    def test_link(self):
        project = self.create_link()
        self.verify_subproject(project, 3, 'cs', 4)

    def test_extra_file(self):
        """
        Extra commit file validation.
        """
        project = self.create_subproject()
        project.full_clean()

        project.extra_commit_file = 'locale/list.txt'
        project.full_clean()

        project.extra_commit_file = 'locale/%(language)s.txt'
        project.full_clean()

        project.extra_commit_file = 'locale/%(bar)s.txt'
        self.assertRaisesMessage(
            ValidationError,
            "Bad format string ('bar')",
            project.full_clean
        )

    def test_check_flags(self):
        """
        Check flags validation.
        """
        project = self.create_subproject()
        project.full_clean()

        project.check_flags = 'ignore-inconsistent'
        project.full_clean()

        project.check_flags = 'rst-text,ignore-inconsistent'
        project.full_clean()

        project.check_flags = 'nonsense'
        self.assertRaisesMessage(
            ValidationError,
            'Invalid check flag: "nonsense"',
            project.full_clean
        )

        project.check_flags = 'rst-text,ignore-nonsense'
        self.assertRaisesMessage(
            ValidationError,
            'Invalid check flag: "ignore-nonsense"',
            project.full_clean
        )

    def test_lang_code_template(self):
        subproject = SubProject(project=Project())
        subproject.filemask = 'Solution/Project/Resources.*.resx'
        subproject.template = 'Solution/Project/Resources.resx'
        self.assertEqual(
            subproject.get_lang_code('Solution/Project/Resources.resx'),
            'en'
        )


class SubProjectDeleteTest(RepoTestCase):
    """
    SubProject object deleting testing.
    """
    def test_delete(self):
        project = self.create_subproject()
        self.assertTrue(os.path.exists(project.get_path()))
        project.delete()
        self.assertFalse(os.path.exists(project.get_path()))
        self.assertEqual(0, SubProject.objects.count())

    @OverrideSettings(OFFLOAD_INDEXING=False)
    def test_delete_no_offload(self):
        project = self.create_subproject()
        project.delete()
        self.assertEqual(0, IndexUpdate.objects.count())

    @OverrideSettings(OFFLOAD_INDEXING=True)
    def test_delete_offload(self):
        project = self.create_subproject()
        project.delete()
        self.assertEqual(
            12, IndexUpdate.objects.count()
        )
        self.assertEqual(
            12, IndexUpdate.objects.filter(to_delete=True).count()
        )

    def test_delete_link(self):
        project = self.create_link()
        main_project = SubProject.objects.get(slug='test')
        self.assertTrue(os.path.exists(main_project.get_path()))
        project.delete()
        self.assertTrue(os.path.exists(main_project.get_path()))

    def test_delete_all(self):
        project = self.create_subproject()
        self.assertTrue(os.path.exists(project.get_path()))
        SubProject.objects.all().delete()
        self.assertFalse(os.path.exists(project.get_path()))


class SubProjectChangeTest(RepoTestCase):
    """
    SubProject object change testing.
    """
    def test_rename(self):
        subproject = self.create_subproject()
        old_path = subproject.get_path()
        self.assertTrue(os.path.exists(old_path))
        subproject.slug = 'changed'
        subproject.save()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(subproject.get_path()))

    def test_change_project(self):
        subproject = self.create_subproject()

        # Create and verify suggestion
        Suggestion.objects.create(
            project=subproject.project,
            contentsum='x',
            language=subproject.translation_set.all()[0].language,
        )
        self.assertEqual(subproject.project.suggestion_set.count(), 1)

        # Check current path exists
        old_path = subproject.get_path()
        self.assertTrue(os.path.exists(old_path))

        # Crete target project
        second = Project.objects.create(
            name='Test2',
            slug='test2',
            web='https://weblate.org/'
        )

        # Move component
        subproject.project = second
        subproject.save()

        # Check new path exists
        new_path = subproject.get_path()
        self.assertTrue(os.path.exists(new_path))

        # Check paths differ
        self.assertNotEqual(old_path, new_path)

        # Check suggestion has been copied
        self.assertEqual(subproject.project.suggestion_set.count(), 1)

    def test_change_to_mono(self):
        """Test swtiching to monolingual format on the fly."""
        component = self._create_subproject(
            'po',
            'po-mono/*.po',
        )
        self.assertEqual(component.translation_set.count(), 4)
        component.file_format = 'po-mono'
        component.template = 'po-mono/en.po'
        component.save()
        self.assertEqual(component.translation_set.count(), 4)


class SubProjectValidationTest(RepoTestCase):
    """
    SubProject object validation testing.
    """
    def setUp(self):
        super(SubProjectValidationTest, self).setUp()
        self.component = self.create_subproject()
        # Ensure we have correct component
        self.component.full_clean()

    def test_commit_message(self):
        """Invalid commit message"""
        self.component.commit_message = '%(foo)s'
        self.assertRaisesMessage(
            ValidationError,
            'Bad format string',
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

        # Check that it warns about not supported format
        self.assertRaisesMessage(
            ValidationError,
            'Chosen file format does not support adding new '
            'translations as chosen in project settings.',
            self.component.full_clean
        )

        self.component.file_format = 'po'
        self.component.save()

        # Clean class cache, pylint: disable=W0212
        self.component._file_format = None

        # With correct format it should validate
        self.component.full_clean()

    def test_lang_code(self):
        subproject = SubProject()
        subproject.filemask = 'Solution/Project/Resources.*.resx'
        self.assertEqual(
            subproject.get_lang_code('Solution/Project/Resources.es-mx.resx'),
            'es-mx'
        )
        self.assertEqual(
            subproject.get_lang_code('Solution/Project/Resources.resx'),
            ''
        )
        self.assertRaisesMessage(
            ValidationError,
            'Got empty language code for '
            'Solution/Project/Resources.resx, please check filemask!',
            subproject.clean_lang_codes,
            [
                'Solution/Project/Resources.resx',
                'Solution/Project/Resources.de.resx',
                'Solution/Project/Resources.es.resx',
                'Solution/Project/Resources.es-mx.resx',
                'Solution/Project/Resources.fr.resx',
                'Solution/Project/Resources.fr-fr.resx',
            ]
        )


class SubProjectErrorTest(RepoTestCase):
    """Tests for error handling"""

    def setUp(self):
        super(SubProjectErrorTest, self).setUp()
        self.component = self.create_ts_mono()
        # Change to invalid pull/push URL
        self.component.repository.configure_remote(
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
        testfile = os.path.join(self.component.get_path(), 'README.md')
        with open(testfile, 'a') as handle:
            handle.write('CHANGE')
        self.component.repository.commit('test', files=['README.md'])
        self.assertFalse(
            self.component.do_push(None)
        )

    def test_failed_reset(self):
        # Corrupt Git database so that reset fails
        shutil.rmtree(
            os.path.join(self.component.get_path(), '.git', 'objects', 'pack')
        )
        self.assertFalse(
            self.component.do_reset(None)
        )

    def test_invalid_templatename(self):
        self.component.template = 'foo.bar'
        # Clean class cache, pylint: disable=W0212
        self.component._template_store = None

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
        testfile = os.path.join(self.component.get_path(), 'ts-mono', 'cs.ts')
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
        testfile = os.path.join(self.component.get_path(), 'ts-mono', 'en.ts')
        with open(testfile, 'a') as handle:
            handle.write('CHANGE')

        # Clean class cache, pylint: disable=W0212
        self.component._template_store = None

        self.assertRaises(
            ParseError,
            lambda: self.component.template_store
        )
        self.assertRaises(
            ValidationError,
            self.component.clean
        )


class SubProjectEditTest(ViewTestCase):
    """Tests for error handling"""
    def remove_units(self, store):
        store.units = []
        store.save()

    def test_unit_disappear(self):
        translation = self.subproject.translation_set.get(language_code='cs')

        if self.subproject.has_template():
            self.remove_units(self.subproject.template_store.store)
        self.remove_units(translation.store.store)

        # Clean class cache, pylint: disable=W0212
        self.subproject._template_store = None
        translation._store = None

        unit = translation.unit_set.all()[0]
        request = self.get_request('/')

        self.assertFalse(
            unit.translate(request, ['Empty'], False)
        )


class SubProjectEditMonoTest(SubProjectEditTest):
    """Tests for error handling"""
    def create_subproject(self):
        return self.create_ts_mono()

    def remove_units(self, store):
        store.parse(store.XMLskeleton.replace("\n", "").encode('utf-8'))
        store.save()

    def test_unit_add(self):
        translation = self.subproject.translation_set.get(language_code='cs')

        self.remove_units(translation.store.store)

        # Clean class cache, pylint: disable=W0212
        translation._store = None

        unit = translation.unit_set.all()[0]
        request = self.get_request('/')

        self.assertTrue(
            unit.translate(request, ['Empty'], False)
        )
