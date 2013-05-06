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

from trans.checks.same import (
    SameCheck,
)
from trans.tests.checks import Unit, CheckTestCase


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
            Unit(code='en'),
            0
        ))

    def test_same_numbers(self):
        self.do_test(False, ('1:4', '1:4', ''))

    def test_same_copyright(self):
        self.do_test(
            False,
            (
                u'(c) Copyright 2013 Michal Čihař',
                u'(c) Copyright 2013 Michal Čihař',
                ''
            )
        )
        self.do_test(
            False,
            (
                u'© Copyright 2013 Michal Čihař',
                u'© Copyright 2013 Michal Čihař',
                ''
            )
        )

    def test_same_format(self):
        self.do_test(
            False,
            (
                '%d.%m.%Y, %H:%M',
                '%d.%m.%Y, %H:%M',
                'php-format'
            )
        )

        self.do_test(
            True,
            (
                '%d byte',
                '%d byte',
                'php-format'
            )
        )

        self.do_test(
            False,
            (
                '%s %s %s %s %s %s &nbsp; %s',
                '%s %s %s %s %s %s &nbsp; %s',
                'c-format',
            )
        )
