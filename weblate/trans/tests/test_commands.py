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
Tests for management commands.
"""

from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth.models import User

from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.models import (
    Translation, SubProject, Suggestion, IndexUpdate
)
from weblate.runner import main
from weblate.trans.tests.utils import get_test_file
from weblate.accounts.models import Profile

TEST_PO = get_test_file('cs.po')
TEST_COMPONENTS = get_test_file('components.json')


class RunnerTest(TestCase):
    def test_help(self):
        main(['help'])


class ImportProjectTest(RepoTestCase):
    def do_import(self, path=None, **kwargs):
        call_command(
            'import_project',
            'test',
            self.git_repo_path if path is None else path,
            'master',
            '**/*.po',
            **kwargs
        )

    def test_import(self):
        project = self.create_project()
        self.do_import()
        # We should have loaded four subprojects
        self.assertEqual(project.subproject_set.count(), 4)

    def test_import_ignore(self):
        project = self.create_project()
        self.do_import()
        self.do_import()
        # We should have loaded four subprojects
        self.assertEqual(project.subproject_set.count(), 4)

    def test_import_duplicate(self):
        project = self.create_project()
        self.do_import()
        self.do_import(path='weblate://test/po', duplicates=True)
        # We should have loaded eight subprojects
        self.assertEqual(project.subproject_set.count(), 8)

    def test_import_main_1(self, name='po-mono'):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            main_component=name
        )
        # We should have loaded four subprojects
        non_linked = project.subproject_set.exclude(
            repo__startswith='weblate:/'
        )
        self.assertEqual(
            non_linked.count(),
            1
        )
        self.assertEqual(
            non_linked[0].slug,
            name
        )

    def test_import_main_2(self):
        self.test_import_main_1('second-po')

    def test_import_main_invalid(self):
        self.assertRaises(
            CommandError,
            self.test_import_main_1,
            'x-po',
        )

    def test_import_filter(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            language_regex='cs'
        )
        # We should have loaded four subprojects
        self.assertEqual(project.subproject_set.count(), 4)
        for component in project.subproject_set.all():
            self.assertEqual(component.translation_set.count(), 1)

    def test_import_re(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            component_regexp=r'(?P<name>[^/-]*)/.*\.po'
        )
        self.assertEqual(project.subproject_set.count(), 1)

    def test_import_name(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            component_regexp=r'(?P<name>[^/-]*)/.*\.po',
            name_template='Test name'
        )
        self.assertEqual(project.subproject_set.count(), 1)
        self.assertTrue(
            project.subproject_set.filter(name='Test name').exists()
        )

    def test_import_re_missing(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            component_regexp=r'(?P<xname>[^/-]*)/.*\.po'
        )

    def test_import_re_wrong(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            component_regexp=r'(?P<xname>[^/-]*'
        )

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
        self.subproject = self.create_subproject()

    def test_cleanup(self):
        Suggestion.objects.create(
            project=self.subproject.project,
            contentsum='x',
            language=self.subproject.translation_set.all()[0].language,
        )
        call_command(
            'cleanuptrans'
        )
        self.assertEqual(
            Suggestion.objects.count(), 0
        )

    def test_update_index_empty(self):
        call_command(
            'update_index'
        )

    def test_update_index(self):
        IndexUpdate.objects.create(
            unitid=666,
            language_code='fo',
            to_delete=False,
            source=False,
        )
        IndexUpdate.objects.create(
            unitid=777,
            language_code='fo',
            to_delete=False,
            source=False,
        )
        IndexUpdate.objects.create(
            unitid=888,
            language_code='fo',
            to_delete=False,
            source=True,
        )
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

    def test_list_same_checks(self):
        call_command(
            'list_same_checks'
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


class SuggesionCommandTest(RepoTestCase):
    '''
    Test suggestion addding.
    '''
    def setUp(self):
        super(SuggesionCommandTest, self).setUp()
        self.subproject = self.create_subproject()

    def test_add_suggestions(self):
        user = User.objects.create_user(
            'testuser',
            'weblate@example.org',
            'testpassword'
        )
        call_command(
            'add_suggestions', 'test', 'test', 'cs', TEST_PO,
            author=user.email
        )
        translation = self.subproject.translation_set.get(language_code='cs')
        self.assertEqual(translation.have_suggestion, 1)
        profile = Profile.objects.get(user__email=user.email)
        self.assertEqual(profile.suggested, 1)

    def test_default_user(self):
        call_command(
            'add_suggestions', 'test', 'test', 'cs', TEST_PO,
        )
        profile = Profile.objects.get(user__email='noreply@weblate.org')
        self.assertEqual(profile.suggested, 1)

    def test_missing_user(self):
        self.assertRaises(
            CommandError,
            call_command,
            'add_suggestions', 'test', 'test', 'cs', TEST_PO,
            author='foo@example.org',
        )

    def test_missing_project(self):
        self.assertRaises(
            CommandError,
            call_command,
            'add_suggestions', 'test', 'xxx', 'cs', TEST_PO,
        )


class ImportCommandTest(RepoTestCase):
    '''
    Import test.
    '''
    def setUp(self):
        super(ImportCommandTest, self).setUp()
        self.subproject = self.create_subproject()

    def test_import(self):
        call_command(
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            TEST_COMPONENTS,
        )
        self.assertEqual(
            self.subproject.project.subproject_set.count(),
            3
        )
        self.assertEqual(
            Translation.objects.count(),
            8
        )

    def test_invalid_file(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            TEST_PO,
        )

    def test_nonexisting_project(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_json',
            '--main-component', 'test',
            '--project', 'test2',
            '/nonexisting/dfile',
        )

    def test_nonexisting_component(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_json',
            '--main-component', 'test2',
            '--project', 'test',
            '/nonexisting/dfile',
        )

    def test_missing_component(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_json',
            '--project', 'test',
            '/nonexisting/dfile',
        )
