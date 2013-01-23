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
Tests for quality checks.
"""

from weblate.trans.checks.same import (
    SameCheck,
)
from weblate.trans.tests.test_checks import Language, CheckTestCase


class SameCheckTest(CheckTestCase):
    def setUp(self):
        super(SameCheckTest, self).setUp()
        self.check = SameCheck()
        self.test_good_none = ('%(source)s', '%(source)s', 'python-format')
        self.test_good_matching = ('source', 'translation', '')
        self.test_good_ignore = ('alarm', 'alarm', '')
        self.test_failure_1 = ('string', 'string', '')

    def test_same_english(self):
        self.assertFalse(self.check.check_single(
            'source',
            'source',
            '',
            Language('en'),
            None,
            0
        ))
