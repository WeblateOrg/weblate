# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

"""
Tests for unitdata models.
"""

from __future__ import unicode_literals

from django.utils.encoding import force_text

from weblate.checks.models import Check
from weblate.trans.tests.test_views import FixtureTestCase


class UnitdataTestCase(FixtureTestCase):
    def create_check(self, name):
        return Check.objects.create(unit=self.get_unit(), check=name)

    def test_check(self):
        check = self.create_check("same")
        self.assertEqual(
            force_text(check.get_description()), "Source and translation are identical"
        )
        self.assertEqual(check.get_severity(), "warning")
        self.assertTrue(check.get_doc_url().endswith("user/checks.html#check-same"))
        self.assertEqual(force_text(check), "Hello, world!\n: same")

    def test_check_nonexisting(self):
        check = self.create_check("-invalid-")
        self.assertEqual(check.get_description(), "-invalid-")
        self.assertEqual(check.get_severity(), "info")
        self.assertEqual(check.get_doc_url(), "")
