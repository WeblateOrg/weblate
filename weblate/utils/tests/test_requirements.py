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

from django.test import SimpleTestCase

from weblate.utils.requirements import check_version


class RequirementsTest(SimpleTestCase):
    """Testing of requirements checking code."""
    def test_check(self):
        self.assertFalse(check_version(
            '1.0',
            '1.0'
        ))
        self.assertFalse(check_version(
            '1.1',
            '1.0'
        ))
        self.assertTrue(check_version(
            '0.9',
            '1.0'
        ))
        self.assertFalse(check_version(
            '1.0',
            None
        ))
