#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from weblate.trans.tests.test_commands import WeblateComponentCommandTestCase
from weblate.trans.tests.test_models import RepoTestCase


class ListSameCommandTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.component = self.create_component()

    def test_list_same_checks(self):
        output = StringIO()
        call_command("list_same_checks", stdout=output)
        self.assertEqual(1, len(output.getvalue().splitlines()))


class UpdateChecksTest(WeblateComponentCommandTestCase):
    command_name = "updatechecks"
    expected_string = "Processing"


class ListTestCase(SimpleTestCase):
    def test_list_checks(self):
        output = StringIO()
        call_command("list_checks", stdout=output)
        self.assertIn(".. _check-same:", output.getvalue())
