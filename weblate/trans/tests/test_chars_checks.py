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
from weblate.trans.checks.chars import (
    BeginNewlineCheck, EndNewlineCheck,
    BeginSpaceCheck, EndSpaceCheck,
    EndStopCheck, EndColonCheck,
    EndQuestionCheck, EndExclamationCheck,
    EndEllipsisCheck,
    NewlineCountingCheck,
    ZeroWidthSpaceCheck,
)
from weblate.trans.tests.test_checks import Unit, Language


class BeginNewlineCheckTest(TestCase):
    def setUp(self):
        self.check = BeginNewlineCheck()

    def test_newline(self):
        self.assertFalse(self.check.check_single(
            '\nstring',
            '\nstring',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_no_newline_1(self):
        self.assertTrue(self.check.check_single(
            '\nstring',
            ' \nstring',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_no_newline_2(self):
        self.assertTrue(self.check.check_single(
            'string',
            '\nstring',
            '',
            Language('cs'),
            None,
            0
        ))


class EndNewlineCheckTest(TestCase):
    def setUp(self):
        self.check = EndNewlineCheck()

    def test_newline(self):
        self.assertFalse(self.check.check_single(
            'string\n',
            'string\n',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_no_newline_1(self):
        self.assertTrue(self.check.check_single(
            'string\n',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_no_newline_2(self):
        self.assertTrue(self.check.check_single(
            'string',
            'string\n',
            '',
            Language('cs'),
            None,
            0
        ))


class BeginSpaceCheckTest(TestCase):
    def setUp(self):
        self.check = BeginSpaceCheck()

    def test_whitespace(self):
        self.assertFalse(self.check.check_single(
            '   string',
            '   string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_no_whitespace_1(self):
        self.assertTrue(self.check.check_single(
            '  string',
            '    string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_no_whitespace_2(self):
        self.assertTrue(self.check.check_single(
            '    string',
            '  string',
            '',
            Language('cs'),
            None,
            0
        ))


class EndSpaceCheckTest(TestCase):
    def setUp(self):
        self.check = EndSpaceCheck()

    def test_whitespace(self):
        self.assertFalse(self.check.check_single(
            'string  ',
            'string  ',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_no_whitespace_1(self):
        self.assertTrue(self.check.check_single(
            'string  ',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_no_whitespace_2(self):
        self.assertTrue(self.check.check_single(
            'string',
            'string ',
            '',
            Language('cs'),
            None,
            0
        ))


class EndStopCheckTest(TestCase):
    def setUp(self):
        self.check = EndStopCheck()

    def test_no_stop(self):
        self.assertFalse(self.check.check_single(
            'string',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_stop(self):
        self.assertFalse(self.check.check_single(
            'string.',
            'string.',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_stop_1(self):
        self.assertTrue(self.check.check_single(
            'string.',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_stop_2(self):
        self.assertTrue(self.check.check_single(
            'string',
            'string.',
            '',
            Language('cs'),
            None,
            0
        ))


class EndColonCheckTest(TestCase):
    def setUp(self):
        self.check = EndColonCheck()

    def test_no_colon(self):
        self.assertFalse(self.check.check_single(
            'string',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_colon(self):
        self.assertFalse(self.check.check_single(
            'string:',
            'string:',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_colon_1(self):
        self.assertTrue(self.check.check_single(
            'string:',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_colon_2(self):
        self.assertTrue(self.check.check_single(
            'string',
            'string:',
            '',
            Language('cs'),
            None,
            0
        ))


class EndQuestionCheckTest(TestCase):
    def setUp(self):
        self.check = EndQuestionCheck()

    def test_no_question(self):
        self.assertFalse(self.check.check_single(
            'string',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_question(self):
        self.assertFalse(self.check.check_single(
            'string?',
            'string?',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_question_1(self):
        self.assertTrue(self.check.check_single(
            'string?',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_question_2(self):
        self.assertTrue(self.check.check_single(
            'string',
            'string?',
            '',
            Language('cs'),
            None,
            0
        ))


class EndExclamationCheckTest(TestCase):
    def setUp(self):
        self.check = EndExclamationCheck()

    def test_no_exclamation(self):
        self.assertFalse(self.check.check_single(
            'string',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_exclamation(self):
        self.assertFalse(self.check.check_single(
            'string!',
            'string!',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_exclamation_1(self):
        self.assertTrue(self.check.check_single(
            'string!',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_exclamation_2(self):
        self.assertTrue(self.check.check_single(
            'string',
            'string!',
            '',
            Language('cs'),
            None,
            0
        ))


class EndEllipsisCheckTest(TestCase):
    def setUp(self):
        self.check = EndEllipsisCheck()

    def test_no_ellipsis(self):
        self.assertFalse(self.check.check_single(
            'string',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_ellipsis(self):
        self.assertFalse(self.check.check_single(
            u'string…',
            u'string…',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_ellipsis_1(self):
        self.assertTrue(self.check.check_single(
            u'string…',
            'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_missing_ellipsis_2(self):
        self.assertTrue(self.check.check_single(
            'string',
            u'string…',
            '',
            Language('cs'),
            None,
            0
        ))


class NewlineCountingCheckTest(TestCase):
    def setUp(self):
        self.check = NewlineCountingCheck()

    def test_none(self):
        self.assertFalse(self.check.check_single(
            u'string',
            u'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_matching(self):
        self.assertFalse(self.check.check_single(
            u'string\\nstring',
            u'string\\nstring',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_not_matching_1(self):
        self.assertTrue(self.check.check_single(
            u'string\\n\\nstring',
            u'string\\nstring',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_not_matching_2(self):
        self.assertTrue(self.check.check_single(
            u'string\\nstring',
            u'string\\n\\nstring',
            '',
            Language('cs'),
            None,
            0
        ))


class ZeroWidthSpaceCheckTest(TestCase):
    def setUp(self):
        self.check = ZeroWidthSpaceCheck()

    def test_none(self):
        self.assertFalse(self.check.check_single(
            u'string',
            u'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_matching(self):
        self.assertFalse(self.check.check_single(
            u'str\u200bing',
            u'str\u200bing',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_not_matching_1(self):
        self.assertTrue(self.check.check_single(
            u'str\u200bing',
            u'string',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_not_matching_2(self):
        self.assertTrue(self.check.check_single(
            u'string',
            u'str\u200bing',
            '',
            Language('cs'),
            None,
            0
        ))
