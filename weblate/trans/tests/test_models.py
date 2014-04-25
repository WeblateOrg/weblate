# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.test import TestCase
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
import shutil
import os
import git
from weblate.trans.models import Project, SubProject, Unit
from weblate.trans.models import whiteboard as whiteboard_model
from weblate import appsettings
from weblate.trans.tests.test_util import get_test_file

REPOWEB_URL = \
    'https://github.com/nijel/weblate-test/blob/master/%(file)s#L%(line)s'
GIT_URL = 'git://github.com/nijel/weblate-test.git'


class RepoTestCase(TestCase):
    """
    Generic class for tests working with repositories.
    """
    def setUp(self):
        if 'test-repos' in settings.GIT_ROOT:
            test_dir = os.path.join(settings.GIT_ROOT, 'test')
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

        # Path where to clone remote repo for tests
        self.base_repo_path = os.path.join(
            settings.GIT_ROOT,
            'test-base-repo.git'
        )
        # Repository on which tests will be performed
        self.repo_path = os.path.join(
            settings.GIT_ROOT,
            'test-repo.git'
        )

        # Git command wrapper
        cmd = git.Git()

        # Clone repo for testing
        if not os.path.exists(self.base_repo_path):
            cmd.clone(
                '--bare',
                GIT_URL,
                self.base_repo_path
            )

        # Remove possibly existing directory
        if os.path.exists(self.repo_path):
            shutil.rmtree(self.repo_path)

        # Create repository copy for the test
        shutil.copytree(self.base_repo_path, self.repo_path)

        # Remove possibly existing project directory
        test_repo_path = os.path.join(settings.GIT_ROOT, 'test')
        if os.path.exists(test_repo_path):
            shutil.rmtree(test_repo_path)

    def create_project(self):
        """
        Creates test project.
        """
        project = Project.objects.create(
            name='Test',
            slug='test',
            web='http://weblate.org/'
        )
        self.addCleanup(shutil.rmtree, project.get_path(), True)
        return project

    def _create_subproject(self, file_format, mask, template='', new_base=''):
        """
        Creates real test subproject.
        """
        project = self.create_project()
        return SubProject.objects.create(
            name='Test',
            slug='test',
            project=project,
            repo=self.repo_path,
            push=self.repo_path,
            filemask=mask,
            template=template,
            file_format=file_format,
            repoweb=REPOWEB_URL,
            save_history=True,
            new_base=new_base,
        )

    def create_subproject(self):
        """
        Wrapper method for providing test subproject.
        """
        return self._create_subproject(
            'auto',
            'po/*.po',
        )

    def create_po(self):
        return self._create_subproject(
            'po',
            'po/*.po',
        )

    def create_po_new_base(self):
        return self._create_subproject(
            'po',
            'po/*.po',
            new_base='po/hello.pot'
        )

    def create_po_link(self):
        return self._create_subproject(
            'po',
            'po-link/*.po',
        )

    def create_po_mono(self):
        return self._create_subproject(
            'po-mono',
            'po-mono/*.po',
            'po-mono/en.po',
        )

    def create_ts(self, suffix=''):
        return self._create_subproject(
            'ts',
            'ts{0}/*.ts'.format(suffix),
        )

    def create_iphone(self):
        return self._create_subproject(
            'strings',
            'iphone/*.lproj/Localizable.strings',
        )

    def create_android(self):
        return self._create_subproject(
            'aresource',
            'android/values-*/strings.xml',
            'android/values/strings.xml',
        )

    def create_java(self):
        return self._create_subproject(
            'properties',
            'java/swing_messages_*.properties',
            'java/swing_messages.properties',
        )

    def create_xliff(self, name='default'):
        return self._create_subproject(
            'xliff',
            'xliff/*/%s.xlf' % name,
        )

    def create_link(self):
        parent = self.create_iphone()
        return SubProject.objects.create(
            name='Test2',
            slug='test2',
            project=parent.project,
            repo='weblate://test/test',
            file_format='po',
            filemask='po/*.po',
        )


class ProjectTest(RepoTestCase):
    """
    Project object testing.
    """

    def test_create(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.get_path()))
        self.assertTrue(project.slug in project.get_path())

    def test_rename(self):
        project = self.create_project()
        old_path = project.get_path()
        self.assertTrue(os.path.exists(old_path))
        project.slug = 'changed'
        project.save()
        new_path = project.get_path()
        self.addCleanup(shutil.rmtree, new_path, True)
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(new_path))

    def test_delete(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.get_path()))
        project.delete()
        self.assertFalse(os.path.exists(project.get_path()))

    def test_delete_all(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.get_path()))
        Project.objects.all().delete()
        self.assertFalse(os.path.exists(project.get_path()))

    def test_wrong_path(self):
        project = self.create_project()

        backup = appsettings.GIT_ROOT
        appsettings.GIT_ROOT = '/weblate-nonexisting-path'

        # Invalidate cache, pylint: disable=W0212
        project._dir_path = None

        self.assertRaisesMessage(
            ValidationError,
            'Could not create project directory',
            project.full_clean
        )

        appsettings.GIT_ROOT = backup

    def test_validation(self):
        project = self.create_project()
        # Correct project
        project.full_clean()
        # Invalid commit message
        project.commit_message = '%(foo)s'
        self.assertRaisesMessage(
            ValidationError,
            'Bad format string',
            project.full_clean
        )

    def test_acl(self):
        """
        Test for ACL handling.
        """
        # Create user to verify ACL
        user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )

        # Create project
        project = self.create_project()

        # Enable ACL
        project.enable_acl = True
        project.save()

        # Check user does not have access
        self.assertFalse(project.has_acl(user))

        # Add ACL
        permission = Permission.objects.get(codename='weblate_acl_test')
        user.user_permissions.add(permission)

        # Need to fetch user again to clear permission cache
        user = User.objects.get(username='testuser')

        # We now should have access
        self.assertTrue(project.has_acl(user))


class SubProjectTest(RepoTestCase):
    """
    SubProject object testing.
    """
    def verify_subproject(self, project, translations, lang, units,
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

    def test_rename(self):
        subproject = self.create_subproject()
        old_path = subproject.get_path()
        self.assertTrue(os.path.exists(old_path))
        subproject.slug = 'changed'
        subproject.save()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(subproject.get_path()))

    def test_delete(self):
        project = self.create_subproject()
        self.assertTrue(os.path.exists(project.get_path()))
        project.delete()
        self.assertFalse(os.path.exists(project.get_path()))

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

    def test_create_po_pot(self):
        project = self._create_subproject(
            'po',
            'po/*.po',
            'po/project.pot'
        )
        self.verify_subproject(project, 3, 'cs', 4, fail=True)

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

    def test_create_po_link(self):
        project = self.create_po_link()
        self.verify_subproject(project, 3, 'cs', 4)

    def test_create_po_mono(self):
        project = self.create_po_mono()
        self.verify_subproject(project, 3, 'cs', 4)

    def test_create_android(self):
        project = self.create_android()
        self.verify_subproject(project, 1, 'cs', 4)

    def test_create_java(self):
        project = self.create_java()
        self.verify_subproject(project, 2, 'cs', 4)

    def test_create_xliff(self):
        project = self.create_xliff()
        self.verify_subproject(project, 1, 'cs', 4)

    def test_create_xliff_dph(self):
        project = self.create_xliff('DPH')
        self.verify_subproject(project, 1, 'en', 9, 'DPH')

    def test_create_xliff_empty(self):
        project = self.create_xliff('EMPTY')
        self.verify_subproject(project, 1, 'en', 6, 'DPH')

    def test_create_xliff_resname(self):
        project = self.create_xliff('Resname')
        self.verify_subproject(project, 1, 'en', 2, 'Hi')

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

    def test_validation(self):
        project = self.create_subproject()
        # Correct project
        project.full_clean()

        # Invalid mask
        project.filemask = 'foo/x.po'
        self.assertRaisesMessage(
            ValidationError,
            'File mask does not contain * as a language placeholder!',
            project.full_clean
        )
        # Not matching mask
        project.filemask = 'foo/*.po'
        self.assertRaisesMessage(
            ValidationError,
            'The mask did not match any files!',
            project.full_clean
        )
        # Unknown file format
        project.filemask = 'iphone/*.lproj/Localizable.strings'
        self.assertRaisesMessage(
            ValidationError,
            'Format of 1 matched files could not be recognized.',
            project.full_clean
        )

        # Repoweb
        project.repoweb = 'http://%(foo)s/%(bar)s/%72'
        self.assertRaisesMessage(
            ValidationError,
            "Bad format string ('foo')",
            project.full_clean
        )

        # Bad link
        project.repo = 'weblate://foo'
        project.push = ''
        self.assertRaisesMessage(
            ValidationError,
            'Invalid link to Weblate project, '
            'use weblate://project/subproject.',
            project.full_clean
        )

        # Bad link
        project.repo = 'weblate://foo/bar'
        project.push = ''
        self.assertRaisesMessage(
            ValidationError,
            'Invalid link to Weblate project, '
            'use weblate://project/subproject.',
            project.full_clean
        )

    def test_validation_mono(self):
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

    def test_validation_newlang(self):
        subproject = self.create_subproject()
        subproject.new_base = 'po/project.pot'
        subproject.save()

        # Check that it warns about unused pot
        self.assertRaisesMessage(
            ValidationError,
            'Base file for new translations is not used '
            'because of project settings.',
            subproject.full_clean
        )

        subproject.project.new_lang = 'add'
        subproject.project.save()

        # Check that it warns about not supported format
        self.assertRaisesMessage(
            ValidationError,
            'Chosen file format does not support adding new '
            'translations as chosen in project settings.',
            subproject.full_clean
        )

        subproject.file_format = 'po'
        subproject.save()

        # Clean class cache, pylint: disable=W0212
        subproject._file_format = None

        # With correct format it should validate
        subproject.full_clean()


class TranslationTest(RepoTestCase):
    """
    Translation testing.
    """
    def test_basic(self):
        project = self.create_subproject()
        translation = project.translation_set.get(language_code='cs')
        self.assertEqual(translation.translated, 0)
        self.assertEqual(translation.total, 4)
        self.assertEqual(translation.fuzzy, 0)

    def test_extra_file(self):
        """
        Test extra commit file handling.
        """
        subproject = self.create_subproject()
        subproject.pre_commit_script = get_test_file(
            '../../../../examples/hook-generate-mo'
        )
        appsettings.SCRIPT_CHOICES.append(
            (subproject.pre_commit_script, 'hook-generate-mo')
        )
        subproject.extra_commit_file = 'po/%(language)s.mo'
        subproject.save()
        subproject.full_clean()
        translation = subproject.translation_set.get(language_code='cs')
        # change backend file
        with open(translation.get_filename(), 'a') as handle:
            handle.write(' ')
        # Test committing
        translation.git_commit(
            None, 'TEST <test@example.net>', timezone.now(),
            force_commit=True
        )

    def test_validation(self):
        """
        Translation validation
        """
        project = self.create_subproject()
        translation = project.translation_set.get(language_code='cs')
        translation.full_clean()


class WhiteboardMessageTest(TestCase):
    """Test(s) for WhiteboardMessage model."""

    def test_can_be_imported(self):
        """Test that whiteboard model can be imported.

        Rather dumb test just to make sure there are no obvious parsing errors.
        """
        _ = whiteboard_model.WhiteboardMessage