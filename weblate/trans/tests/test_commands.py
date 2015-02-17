# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
Tests for management commands.
"""

from django.test import TestCase
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.models import SubProject
from django.core.management import call_command
from django.core.management.base import CommandError


class ImportProjectTest(RepoTestCase):
    def test_import(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
        )
        # We should have loaded four subprojects
        self.assertEqual(project.subproject_set.count(), 4)

    def test_import_po(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            file_format='po'
        )
        # We should have loaded four subprojects
        self.assertEqual(project.subproject_set.count(), 4)

    def test_import_invalid(self):
        project = self.create_project()
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            file_format='INVALID'
        )
        # We should have loaded none subprojects
        self.assertEqual(project.subproject_set.count(), 0)

    def test_import_aresource(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/values-*/strings.xml',
            file_format='aresource',
            base_file_template='android/values/strings.xml',
        )
        # We should have loaded one subproject
        self.assertEqual(project.subproject_set.count(), 1)

    def test_import_aresource_format(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/values-*/strings.xml',
            file_format='aresource',
            base_file_template='%s/values/strings.xml',
        )
        # We should have loaded one subproject
        self.assertEqual(project.subproject_set.count(), 1)

    def test_re_import(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
        )
        # We should have loaded four subprojects
        self.assertEqual(project.subproject_set.count(), 4)

        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
        )
        # We should load no more subprojects
        self.assertEqual(project.subproject_set.count(), 4)

    def test_import_against_existing(self):
        '''
        Test importing with a weblate:// URL
        '''
        android = self.create_android()
        project = android.project
        self.assertEqual(project.subproject_set.count(), 1)
        call_command(
            'import_project',
            project.slug,
            'weblate://%s/%s' % (project.slug, android.slug),
            'master',
            '**/*.po',
        )
        # We should have loaded five subprojects
        self.assertEqual(project.subproject_set.count(), 5)

    def test_import_missing_project(self):
        '''
        Test of correct handling of missing project.
        '''
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
        )

    def test_import_missing_wildcard(self):
        '''
        Test of correct handling of missing wildcard.
        '''
        self.create_project()
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '*/*.po',
        )


class BasicCommandTest(TestCase):
    def test_versions(self):
        call_command('list_versions')


class PeriodicCommandTest(RepoTestCase):
    def setUp(self):
        super(PeriodicCommandTest, self).setUp()
        self.create_subproject()

    def test_cleanup(self):
        call_command(
            'cleanuptrans'
        )

    def test_update_index(self):
        # Test the command
        call_command(
            'update_index'
        )

    def test_list_checks(self):
        call_command(
            'list_ignored_checks'
        )
        call_command(
            'list_ignored_checks',
            list_all=True
        )
        call_command(
            'list_ignored_checks',
            count=10
        )


class CheckGitTest(RepoTestCase):
    '''
    Base class for handling tests of WeblateCommand
    based commands.
    '''
    command_name = 'checkgit'

    def setUp(self):
        super(CheckGitTest, self).setUp()
        self.create_subproject()

    def do_test(self, *args, **kwargs):
        call_command(
            self.command_name,
            *args,
            **kwargs
        )

    def test_all(self):
        self.do_test(
            all=True,
        )

    def test_project(self):
        self.do_test(
            'test',
        )

    def test_subproject(self):
        self.do_test(
            'test/test',
        )

    def test_nonexisting_project(self):
        self.assertRaises(
            CommandError,
            self.do_test,
            'notest',
        )

    def test_nonexisting_subproject(self):
        self.assertRaises(
            CommandError,
            self.do_test,
            'test/notest',
        )


class CommitPendingTest(CheckGitTest):
    command_name = 'commit_pending'


class CommitGitTest(CheckGitTest):
    command_name = 'commitgit'


class PushGitTest(CheckGitTest):
    command_name = 'pushgit'


class LoadTest(CheckGitTest):
    command_name = 'loadpo'


class UpdateChecksTest(CheckGitTest):
    command_name = 'updatechecks'


class UpdateGitTest(CheckGitTest):
    command_name = 'updategit'


class RebuildIndexTest(CheckGitTest):
    command_name = 'rebuild_index'

    def test_all_clean(self):
        self.do_test(
            all=True,
            clean=True,
        )


class LockTranslationTest(CheckGitTest):
    command_name = 'lock_translation'


class UnLockTranslationTest(CheckGitTest):
    command_name = 'unlock_translation'


class FixupFlagsTest(CheckGitTest):
    command_name = 'fixup_flags'


class LockingCommandTest(RepoTestCase):
    '''
    Test locking and unlocking.
    '''
    def setUp(self):
        super(LockingCommandTest, self).setUp()
        self.create_subproject()

    def test_locking(self):
        subproject = SubProject.objects.all()[0]
        self.assertFalse(
            SubProject.objects.filter(locked=True).exists()
        )
        call_command(
            'lock_translation',
            '{0}/{1}'.format(
                subproject.project.slug,
                subproject.slug,
            )
        )
        self.assertTrue(
            SubProject.objects.filter(locked=True).exists()
        )
        call_command(
            'unlock_translation',
            '{0}/{1}'.format(
                subproject.project.slug,
                subproject.slug,
            )
        )
        self.assertFalse(
            SubProject.objects.filter(locked=True).exists()
        )


class BenchmarkCommandTest(RepoTestCase):
    '''
    Benchmarking test.
    '''
    def setUp(self):
        super(BenchmarkCommandTest, self).setUp()
        self.create_subproject()

    def test_benchmark(self):
        call_command(
            'benchmark', 'test', 'weblate://test/test', 'po/*.po'
        )
