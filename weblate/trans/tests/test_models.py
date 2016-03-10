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

from __future__ import print_function

from unittest import SkipTest
import shutil
import os

from django.test import TestCase
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError

from weblate.trans.formats import FILE_FORMATS
from weblate.trans.models import (
    Project, SubProject, Source, Unit, WhiteboardMessage, Check, ComponentList,
    get_related_units,
)
from weblate import appsettings
from weblate.trans.tests import OverrideSettings
from weblate.trans.tests.utils import get_test_file
from weblate.trans.vcs import GitRepository, HgRepository
from weblate.trans.search import clean_indexes

REPOWEB_URL = \
    'https://github.com/nijel/weblate-test/blob/master/%(file)s#L%(line)s'
GIT_URL = 'git://github.com/nijel/weblate-test.git'
HG_URL = 'https://nijel@bitbucket.org/nijel/weblate-test'


class RepoTestCase(TestCase):
    """
    Generic class for tests working with repositories.
    """
    def setUp(self):
        # Path where to clone remote repo for tests
        self.git_base_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-base-repo.git'
        )
        # Repository on which tests will be performed
        self.git_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-repo.git'
        )

        # Path where to clone remote repo for tests
        self.hg_base_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-base-repo.hg'
        )
        # Repository on which tests will be performed
        self.hg_repo_path = os.path.join(
            settings.DATA_DIR,
            'test-repo.hg'
        )

        # Clone repo for testing
        if not os.path.exists(self.git_base_repo_path):
            print(
                'Cloning Git test repository to {0}...'.format(
                    self.git_base_repo_path
                )
            )
            GitRepository.clone(
                GIT_URL,
                self.git_base_repo_path,
                bare=True
            )

        # Remove possibly existing directory
        if os.path.exists(self.git_repo_path):
            shutil.rmtree(self.git_repo_path)

        # Create repository copy for the test
        shutil.copytree(self.git_base_repo_path, self.git_repo_path)

        if HgRepository.is_supported():
            # Clone repo for testing
            if not os.path.exists(self.hg_base_repo_path):
                print(
                    'Cloning Mercurial test repository to {0}...'.format(
                        self.hg_base_repo_path
                    )
                )
                HgRepository.clone(
                    HG_URL,
                    self.hg_base_repo_path,
                    bare=True
                )

            # Remove possibly existing directory
            if os.path.exists(self.hg_repo_path):
                shutil.rmtree(self.hg_repo_path)

            # Create repository copy for the test
            shutil.copytree(self.hg_base_repo_path, self.hg_repo_path)

        # Remove possibly existing project directory
        test_repo_path = os.path.join(settings.DATA_DIR, 'vcs', 'test')
        if os.path.exists(test_repo_path):
            shutil.rmtree(test_repo_path)

        # Remove indexes
        clean_indexes()

    def create_project(self):
        """
        Creates test project.
        """
        project = Project.objects.create(
            name='Test',
            slug='test',
            web='https://weblate.org/'
        )
        self.addCleanup(shutil.rmtree, project.get_path(), True)
        return project

    def _create_subproject(self, file_format, mask, template='',
                           new_base='', vcs='git', **kwargs):
        """
        Creates real test subproject.
        """
        project = self.create_project()

        if vcs == 'mercurial':
            branch = 'default'
            repo = self.hg_repo_path
            push = self.hg_repo_path
            if not HgRepository.is_supported():
                raise SkipTest('Mercurial not available!')
        else:
            branch = 'master'
            repo = self.git_repo_path
            push = self.git_repo_path

        if 'new_lang' not in kwargs:
            kwargs['new_lang'] = 'contact'

        return SubProject.objects.create(
            name='Test',
            slug='test',
            project=project,
            repo=repo,
            push=push,
            branch=branch,
            filemask=mask,
            template=template,
            file_format=file_format,
            repoweb=REPOWEB_URL,
            save_history=True,
            new_base=new_base,
            vcs=vcs,
            **kwargs
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

    def create_po_empty(self):
        return self._create_subproject(
            'po',
            'po-empty/*.po',
            new_base='po-empty/hello.pot',
            new_lang='add',
        )

    def create_po_mercurial(self):
        return self._create_subproject(
            'po',
            'po/*.po',
            vcs='mercurial'
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

    def create_ts_mono(self):
        return self._create_subproject(
            'ts',
            'ts-mono/*.ts',
            'ts-mono/en.ts',
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

    def create_json(self):
        return self._create_subproject(
            'json',
            'json/*.json',
        )

    def create_json_mono(self):
        return self._create_subproject(
            'json',
            'json-mono/*.json',
            'json-mono/en.json',
        )

    def create_tsv(self):
        return self._create_subproject(
            'csv',
            'tsv/*.txt',
        )

    def create_csv(self):
        return self._create_subproject(
            'csv',
            'csv/*.txt',
        )

    def create_csv_mono(self):
        return self._create_subproject(
            'csv',
            'csv-mono/*.csv',
            'csv-mono/en.csv',
        )

    def create_php_mono(self):
        return self._create_subproject(
            'php',
            'php-mono/*.php',
            'php-mono/en.php',
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

    def create_xliff_mono(self):
        return self._create_subproject(
            'xliff',
            'xliff-mono/*.xlf',
            'xliff-mono/en.xlf',
        )

    def create_resx(self):
        if 'resx' not in FILE_FORMATS:
            raise SkipTest('resx not supported')
        return self._create_subproject(
            'resx',
            'resx/*.resx',
            'resx/en.resx',
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
            new_lang='contact',
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

        with OverrideSettings(DATA_DIR='/weblate-nonexisting-path'):
            # Invalidate cache, pylint: disable=W0212
            project._dir_path = None

            self.assertRaisesMessage(
                ValidationError,
                'Could not create project directory',
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
        appsettings.PRE_COMMIT_SCRIPT_CHOICES.append(
            (subproject.pre_commit_script, 'hook-generate-mo')
        )
        subproject.pre_commit_script = get_test_file(
            '../../../../examples/hook-update-linguas'
        )
        appsettings.PRE_COMMIT_SCRIPT_CHOICES.append(
            (subproject.pre_commit_script, 'hook-update-linguas')
        )
        subproject.extra_commit_file = 'po/%(language)s.mo\npo/LINGUAS'
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
        linguas = os.path.join(subproject.get_path(), 'po', 'LINGUAS')
        with open(linguas, 'r') as handle:
            data = handle.read()
            self.assertIn('\ncs\n', data)
        self.assertFalse(translation.repo_needs_commit())

    def test_validation(self):
        """
        Translation validation
        """
        project = self.create_subproject()
        translation = project.translation_set.get(language_code='cs')
        translation.full_clean()

    def test_update_stats(self):
        """
        Check update stats with no units.
        """
        project = self.create_subproject()
        translation = project.translation_set.get(language_code='cs')
        translation.update_stats()
        translation.unit_set.all().delete()
        translation.update_stats()


class WhiteboardMessageTest(TestCase):
    """Test(s) for WhiteboardMessage model."""

    def test_can_be_imported(self):
        """Test that whiteboard model can be imported.

        Rather dumb test just to make sure there are no obvious parsing errors.
        """
        WhiteboardMessage()


class ComponentListTest(TestCase):
    """Test(s) for ComponentList model."""

    def test_can_be_imported(self):
        """Test that ComponentList model can be imported.

        Rather dumb test just to make sure there are no obvious parsing errors.
        """
        ComponentList()


class ModelTestCase(RepoTestCase):
    def setUp(self):
        super(ModelTestCase, self).setUp()
        self.subproject = self.create_subproject()


class SourceTest(ModelTestCase):
    """
    Source objects testing.
    """
    def test_exists(self):
        self.assertTrue(Source.objects.exists())

    def test_source_info(self):
        unit = Unit.objects.all()[0]
        self.assertIsNotNone(unit.source_info)

    def test_priority(self):
        unit = Unit.objects.all()[0]
        self.assertEqual(unit.priority, 100)
        source = unit.source_info
        source.priority = 200
        source.save()
        unit2 = Unit.objects.get(pk=unit.pk)
        self.assertEqual(unit2.priority, 200)

    def test_check_flags(self):
        """
        Setting of Source check_flags changes checks for related units.
        """
        self.assertEqual(Check.objects.count(), 3)
        check = Check.objects.all()[0]
        unit = get_related_units(check)[0]
        source = unit.source_info
        source.check_flags = 'ignore-{0}'.format(check.check)
        source.save()
        self.assertEqual(Check.objects.count(), 0)


class UnitTest(ModelTestCase):
    @OverrideSettings(MT_WEBLATE_LIMIT=15)
    def test_more_like(self):
        unit = Unit.objects.all()[0]
        self.assertEqual(Unit.objects.more_like_this(unit).count(), 0)

    @OverrideSettings(MT_WEBLATE_LIMIT=0)
    def test_more_like_timeout(self):
        unit = Unit.objects.all()[0]
        self.assertRaisesMessage(
            Exception, 'Request timed out.', Unit.objects.more_like_this, unit
        )

    @OverrideSettings(MT_WEBLATE_LIMIT=-1)
    def test_more_like_no_fork(self):
        unit = Unit.objects.all()[0]
        self.assertEqual(Unit.objects.more_like_this(unit).count(), 0)
