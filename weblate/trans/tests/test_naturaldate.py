# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
'''
Testing of natural time conversion.
'''

from unittest import TestCase
from weblate.trans.templatetags.translations import naturaltime
import datetime

TEST_DATA = (
    (0, 'now'),
    (1, 'a second from now'),
    (-1, 'a second ago'),
    (2, '2 seconds from now'),
    (-2, '2 seconds ago'),
    (60, 'a minute from now'),
    (-60, 'a minute ago'),
    (120, '2 minutes from now'),
    (-120, '2 minutes ago'),
    (3600, 'an hour from now'),
    (-3600, 'an hour ago'),
    (3600 * 2, '2 hours from now'),
    (-3600 * 2, '2 hours ago'),
    (3600 * 24, 'tomorrow'),
    (-3600 * 24, 'yesterday'),
    (3600 * 24 * 2, '2 days from now'),
    (-3600 * 24 * 2, '2 days ago'),
    (3600 * 24 * 7, 'a week from now'),
    (-3600 * 24 * 7, 'a week ago'),
    (3600 * 24 * 14, '2 weeks from now'),
    (-3600 * 24 * 14, '2 weeks ago'),
    (3600 * 24 * 30, 'a month from now'),
    (-3600 * 24 * 30, 'a month ago'),
    (3600 * 24 * 60, '2 months from now'),
    (-3600 * 24 * 60, '2 months ago'),
    (3600 * 24 * 365, 'a year from now'),
    (-3600 * 24 * 365, 'a year ago'),
    (3600 * 24 * 365 * 2, '2 years from now'),
    (-3600 * 24 * 365 * 2, '2 years ago'),
)


class NaturalTimeTest(TestCase):
    def test_natural(self):
        now = datetime.datetime.now()
        for diff, expected in TEST_DATA:
            testdate = now + datetime.timedelta(seconds=diff)
            result = naturaltime(testdate, now)
            self.assertEqual(
                expected, result,
                'naturaltime(%s) [%s] != "%s"' % (
                    testdate, result, expected,
                )
            )
