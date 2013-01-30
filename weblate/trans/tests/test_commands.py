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

class WeblateCommandTest(RepoTestCase):
    '''
    Base class for handling tests of WeblateCommand
    based commands.
    '''
    command_name = None

    def do_test(self, *args, **kwargs):
        resource = self.create_subproject()
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


class LoadTest(WeblateCommandTest):
    command_name = 'loadpo'


class UpdateChecksTest(WeblateCommandTest):
    command_name = 'updatechecks'


class UpdateGitTest(WeblateCommandTest):
    command_name = 'updategit'
