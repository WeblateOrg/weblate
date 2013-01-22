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

from django.test import TestCase
from weblate.trans.checks.markup import (
    BBCodeCheck,
    XMLTagsCheck,
)
from weblate.trans.tests.test_checks import Unit, Language


class BBCodeCheckTest(TestCase):
    def setUp(self):
        self.check = BBCodeCheck()

    def test_none(self):
        self.assertFalse(self.check.check_single(
            u'string',
            u'string',
            '',
            Language('cs'),
            Unit('bbcode_none'),
            0
        ))

    def test_matching(self):
        self.assertFalse(self.check.check_single(
            u'[a]string[/a]',
            u'[a]string[/a]',
            '',
            Language('cs'),
            Unit('bbcode_matching'),
            0
        ))

    def test_not_matching_1(self):
        self.assertTrue(self.check.check_single(
            u'[a]string[/a]',
            u'[b]string[/b]',
            '',
            Language('cs'),
            Unit('bbcode_not_matching_1'),
            0
        ))

    def test_not_matching_2(self):
        self.assertTrue(self.check.check_single(
            u'[a]string[/a]',
            u'[a]string[/b]',
            '',
            Language('cs'),
            Unit('bbcode_not_matching_2'),
            0
        ))


class XMLTagsCheckTest(TestCase):
    def setUp(self):
        self.check = XMLTagsCheck()

    def test_none(self):
        self.assertFalse(self.check.check_single(
            u'string',
            u'string',
            '',
            Language('cs'),
            Unit('xml_none'),
            0
        ))
        self.assertFalse(self.check.check_single(
            u'string',
            u'string',
            '',
            Language('de'),
            Unit('xml_none'),
            0
        ))

    def test_invalid(self):
        self.assertFalse(self.check.check_single(
            u'string</a>',
            u'string</a>',
            '',
            Language('cs'),
            Unit('xml_invalid'),
            0
        ))
        self.assertFalse(self.check.check_single(
            u'string</a>',
            u'string</a>',
            '',
            Language('de'),
            Unit('xml_invalid'),
            0
        ))

    def test_matching(self):
        self.assertFalse(self.check.check_single(
            u'<a>string</a>',
            u'<a>string</a>',
            '',
            Language('cs'),
            Unit('xml_matching'),
            0
        ))
        self.assertFalse(self.check.check_single(
            u'<a>string</a>',
            u'<a>string</a>',
            '',
            Language('de'),
            Unit('xml_matching'),
            0
        ))

    def test_not_matching_1(self):
        self.assertTrue(self.check.check_single(
            u'<a>string</a>',
            u'<b>string</b>',
            '',
            Language('cs'),
            Unit('xml_not_matching_1'),
            0
        ))

    def test_not_matching_2(self):
        self.assertTrue(self.check.check_single(
            u'<a>string</a>',
            u'<a>string</b>',
            '',
            Language('cs'),
            Unit('xml_not_matching_2'),
            0
        ))
