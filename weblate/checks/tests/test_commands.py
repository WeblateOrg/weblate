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

"""Test for management commands."""

from six import StringIO

from django.core.management import call_command

from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.test_commands import CheckGitTest


class PeriodicCommandTest(RepoTestCase):
    def setUp(self):
        super(PeriodicCommandTest, self).setUp()
        self.component = self.create_component()

    def test_list_checks(self):
        output = StringIO()
        call_command(
            'list_ignored_checks',
            stdout=output
        )
        self.assertEqual('', output.getvalue())

    def test_list_all_checks(self):
        output = StringIO()
        call_command(
            'list_ignored_checks',
            list_all=True,
            stdout=output
        )
        self.assertEqual(2, len(output.getvalue().splitlines()))

    def test_list_count_checks(self):
        output = StringIO()
        call_command(
            'list_ignored_checks',
            count=10,
            stdout=output
        )
        self.assertEqual('', output.getvalue())

    def test_list_same_checks(self):
        output = StringIO()
        call_command(
            'list_same_checks',
            stdout=output
        )
        self.assertEqual(1, len(output.getvalue().splitlines()))


class UpdateChecksTest(CheckGitTest):
    command_name = 'updatechecks'
    expected_string = 'Processing'
