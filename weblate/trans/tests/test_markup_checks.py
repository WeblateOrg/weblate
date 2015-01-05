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

"""
Tests for quality checks.
"""

from weblate.trans.checks.markup import (
    BBCodeCheck,
    XMLTagsCheck,
)
from weblate.trans.tests.test_checks import CheckTestCase


class BBCodeCheckTest(CheckTestCase):
    check = BBCodeCheck()

    def setUp(self):
        super(BBCodeCheckTest, self).setUp()
        self.test_good_matching = ('[a]string[/a]', '[a]string[/a]', '')
        self.test_failure_1 = ('[a]string[/a]', '[b]string[/b]', '')
        self.test_failure_2 = ('[a]string[/a]', 'string', '')


class XMLTagsCheckTest(CheckTestCase):
    check = XMLTagsCheck()

    def setUp(self):
        super(XMLTagsCheckTest, self).setUp()
        self.test_good_matching = ('<a>string</a>', '<a>string</a>', '')
        self.test_failure_1 = ('<a>string</a>', '<b>string</b>', '')
        self.test_failure_2 = ('<a>string</a>', 'string', '')
        self.test_failure_3 = ('<a>string</a>', '<b>string</a>', '')
