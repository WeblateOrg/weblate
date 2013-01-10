# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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
Tests for consistency checks.
"""

from django.test import TestCase
from weblate.trans.checks import (
    SameCheck,
    BeginNewlineCheck, EndNewlineCheck,
    BeginSpaceCheck, EndSpaceCheck,
    EndStopCheck, EndColonCheck,
    EndQuestionCheck, EndExclamationCheck,
    EndEllipsisCheck,
    PythonFormatCheck, PHPFormatCheck, CFormatCheck,
    PluralsCheck,
    NewlineCountingCheck,
    BBCodeCheck,
    ZeroWidthSpaceCheck,
    XMLTagsCheck,
)


class Language(object):
    '''
    Mock language object.
    '''
    def __init__(self, code):
        self.code = code


class Unit(object):
    '''
    Mock unit object.
    '''
    def __init__(self, checksum):
        self.checksum = checksum


class SameCheckTest(TestCase):
    def setUp(self):
        self.check = SameCheck()

    def test_not_same(self):
        self.assertFalse(self.check.check_single(
            'source',
            'translation',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_same(self):
        self.assertTrue(self.check.check_single(
            'source',
            'source',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_same_english(self):
        self.assertFalse(self.check.check_single(
            'source',
            'source',
            '',
            Language('en'),
            None,
            0
        ))

    def test_same_format(self):
        self.assertFalse(self.check.check_single(
            '%(source)s',
            '%(source)s',
            'python-format',
            Language('cs'),
            None,
            0
        ))


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


class PythonFormatCheckTest(TestCase):
    def setUp(self):
        self.check = PythonFormatCheck()

    def test_no_format(self):
        self.assertFalse(self.check.check_format(
            'strins',
            'string',
            'python-format',
            Language('cs'),
            Unit('python_no_format'),
            0,
            False
        ))

    def test_format(self):
        self.assertFalse(self.check.check_format(
            u'%s string',
            u'%s string',
            'python-format',
            Language('cs'),
            Unit('python_format'),
            0,
            False
        ))

    def test_percent_format(self):
        self.assertFalse(self.check.check_format(
            u'%d%% string',
            u'%d%% string',
            'python-format',
            Language('cs'),
            Unit('python_percent_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%(name)s string',
            u'%(name)s string',
            'python-format',
            Language('cs'),
            Unit('python_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'string',
            'python-format',
            Language('cs'),
            Unit('python_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%(name)s string',
            u'string',
            'python-format',
            Language('cs'),
            Unit('python_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'%(name)s string',
            u'string',
            'python-format',
            Language('cs'),
            Unit('python_missing_named_format'),
            0,
           True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%c string',
            'python-format',
            Language('cs'),
            Unit('python_wrong_format'),
            0,
            False
        ))

    def test_wrong_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%(name)s string',
            u'%(jmeno)s string',
            'python-format',
            Language('cs'),
            Unit('python_wrong_named_format'),
            0,
            False
        ))


class PHPFormatCheckTest(TestCase):
    def setUp(self):
        self.check = PHPFormatCheck()

    def test_no_format(self):
        self.assertFalse(self.check.check_format(
            'strins',
            'string',
            'php-format',
            Language('cs'),
            Unit('php_no_format'),
            0,
            False
        ))

    def test_format(self):
        self.assertFalse(self.check.check_format(
            u'%s string',
            u'%s string',
            'php-format',
            Language('cs'),
            Unit('php_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%1$s string',
            u'%1$s string',
            'php-format',
            Language('cs'),
            Unit('php_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'string',
            'php-format',
            Language('cs'),
            Unit('php_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%1$s string',
            u'string',
            'php-format',
            Language('cs'),
            Unit('php_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'%1$s string',
            u'string',
            'php-format',
            Language('cs'),
            Unit('php_missing_named_format'),
            0,
            True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%c string',
            'php-format',
            Language('cs'),
            Unit('php_wrong_format'),
            0,
            False
        ))

    def test_wrong_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%1$s string',
            u'%s string',
            'php-format',
            Language('cs'),
            Unit('php_wrong_named_format'),
            0,
            False
        ))


class CFormatCheckTest(TestCase):
    def setUp(self):
        self.check = CFormatCheck()

    def test_no_format(self):
        self.assertFalse(self.check.check_format(
            'strins',
            'string',
            'c-format',
            Language('cs'),
            Unit('c_no_format'),
            0,
            False
        ))

    def test_format(self):
        self.assertFalse(self.check.check_format(
            u'%s string',
            u'%s string',
            'c-format',
            Language('cs'),
            Unit('c_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%10s string',
            u'%10s string',
            'c-format',
            Language('cs'),
            Unit('c_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'string',
            'c-format',
            Language('cs'),
            Unit('c_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%10s string',
            u'string',
            'c-format',
            Language('cs'),
            Unit('c_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'%10s string',
            u'string',
            'c-format',
            Language('cs'),
            Unit('c_missing_named_format'),
            0,
            True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%c string',
            'c-format',
            Language('cs'),
            Unit('c_wrong_format'),
            0,
            False
        ))

    def test_wrong_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%10s string',
            u'%20s string',
            'c-format',
            Language('cs'),
            Unit('c_wrong_named_format'),
            0,
            False
        ))


class PluralsCheckTest(TestCase):
    def setUp(self):
        self.check = PluralsCheck()

    def test_none(self):
        self.assertFalse(self.check.check(
            ['string'],
            ['string'],
            '',
            Language('cs'),
            None
        ))

    def test_empty(self):
        self.assertFalse(self.check.check(
            ['string', 'plural'],
            ['', ''],
            '',
            Language('cs'),
            None
        ))

    def test_partial_empty(self):
        self.assertTrue(self.check.check(
            ['string', 'plural'],
            ['string', ''],
            '',
            Language('cs'),
            None
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
