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
Helpers for quality checks tests.
"""

from django.test import TestCase
import uuid
import unittest
from weblate.trans.checks.base import Check


class Language(object):
    '''
    Mock language object.
    '''
    def __init__(self, code='cs'):
        self.code = code


class Unit(object):
    '''
    Mock unit object.
    '''
    def __init__(self, checksum=None):
        if checksum is None:
            checksum = str(uuid.uuid1())
        self.checksum = checksum


class CheckTestCase(TestCase):
    '''
    Generic test, also serves for testing base class.
    '''
    def setUp(self):
        self.check = Check()
        self.test_empty = ('', '', '')
        self.test_good_matching = None
        self.test_good_none = ('string', 'string', '')
        self.test_failure_1 = None
        self.test_failure_2 = None

    def do_test(self, expected, data):
        '''
        Performs single check if we have data to test.
        '''
        if data is None:
            return
        self.assertEqual(
            self.check.check_single(
                data[0],
                data[1],
                data[2],
                Language(),
                Unit(),
                0
            ),
            expected
        )

    def test_single_good_matching(self):
        self.do_test(False, self.test_good_matching)

    def test_single_good_none(self):
        self.do_test(False, self.test_good_none)

    def test_single_empty(self):
        self.do_test(False, self.test_empty)

    def test_single_failure_1(self):
        self.do_test(True, self.test_failure_1)

    def test_single_failure_2(self):
        self.do_test(True, self.test_failure_2)
