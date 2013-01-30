# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from weblate.trans.tests.test_models import RepoTestCase
from django.core.management import call_command
from weblate.trans.search import FULLTEXT_INDEX


class ImportTest(RepoTestCase):
    def test_import(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.repo_path,
            'master',
            '**/*.po',
        )
        # We should have loaded two subprojects
        self.assertEqual(project.subproject_set.count(), 2)

    def test_import_missing_project(self):
        '''
        Test of correct handling of missing project.
        '''
        self.assertRaises(
            SystemExit,
            call_command,
            'import_project',
            'test',
            self.repo_path,
            'master',
            '**/*.po',
        )

    def test_import_missing_wildcard(self):
        '''
        Test of correct handling of missing wildcard.
        '''
        project = self.create_project()
        self.assertRaises(
            SystemExit,
            call_command,
            'import_project',
            'test',
            self.repo_path,
            'master',
            '*/*.po',
        )


class PeriodicTest(RepoTestCase):
    def test_cleanup(self):
        call_command(
            'cleanuptrans'
        )

    def test_update_index(self):
        call_command(
            'update_index'
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
            SystemExit,
            self.do_test,
            'notest',
        )

    def test_nonexisting_subproject(self):
        self.assertRaises(
            SystemExit,
            self.do_test,
            'test/notest',
        )


class CommitPendingTest(CheckGitTest):
    command_name = 'commit_pending'


class CommitGitTest(CheckGitTest):
    command_name = 'commitgit'


class LoadTest(CheckGitTest):
    command_name = 'loadpo'


class UpdateChecksTest(CheckGitTest):
    command_name = 'updatechecks'


class UpdateGitTest(CheckGitTest):
    command_name = 'updategit'


class RebuildIndexTest(CheckGitTest):
    command_name = 'rebuild_index'

    def setUp(self):
        super(RebuildIndexTest, self).setUp()
        # Flush possible caches
        FULLTEXT_INDEX._source_writer.commit()
        for lang in FULLTEXT_INDEX._target_writer:
            FULLTEXT_INDEX._target_writer[lang].commit()

    def test_all_clean(self):
        self.do_test(
            all=True,
            clean=True,
        )
