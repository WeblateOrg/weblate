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

"""
Tests for quality checks.
"""

from __future__ import unicode_literals
from unittest import TestCase
from weblate.checks.chars import (
    BeginNewlineCheck, EndNewlineCheck,
    BeginSpaceCheck, EndSpaceCheck,
    EndStopCheck, EndColonCheck,
    EndQuestionCheck, EndExclamationCheck,
    EndEllipsisCheck, EndSemicolonCheck,
    NewlineCountingCheck,
    ZeroWidthSpaceCheck,
    MaxLengthCheck,
)
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit


class BeginNewlineCheckTest(CheckTestCase):
    check = BeginNewlineCheck()

    def setUp(self):
        super(BeginNewlineCheckTest, self).setUp()
        self.test_good_matching = ('\nstring', '\nstring', '')
        self.test_failure_1 = ('\nstring', ' \nstring', '')
        self.test_failure_2 = ('string', '\nstring', '')


class EndNewlineCheckTest(CheckTestCase):
    check = EndNewlineCheck()

    def setUp(self):
        super(EndNewlineCheckTest, self).setUp()
        self.test_good_matching = ('string\n', 'string\n', '')
        self.test_failure_1 = ('string\n', 'string', '')
        self.test_failure_2 = ('string', 'string\n', '')


class BeginSpaceCheckTest(CheckTestCase):
    check = BeginSpaceCheck()

    def setUp(self):
        super(BeginSpaceCheckTest, self).setUp()
        self.test_good_matching = ('   string', '   string', '')
        self.test_good_ignore = ('.', ' ', '')
        self.test_good_none = (' The ', '  ', '')
        self.test_failure_1 = ('  string', '    string', '')
        self.test_failure_2 = ('    string', '  string', '')


class EndSpaceCheckTest(CheckTestCase):
    check = EndSpaceCheck()

    def setUp(self):
        super(EndSpaceCheckTest, self).setUp()
        self.test_good_matching = ('string  ', 'string  ', '')
        self.test_good_ignore = ('.', ' ', '')
        self.test_good_none = (' The ', '  ', '')
        self.test_failure_1 = ('string  ', 'string', '')
        self.test_failure_2 = ('string', 'string ', '')

    def test_french(self):
        self.do_test(False, ('Text!', 'Texte !', ''), 'fr')
        self.do_test(True, ('Text', 'Texte ', ''), 'fr')


class EndStopCheckTest(CheckTestCase):
    check = EndStopCheck()

    def setUp(self):
        super(EndStopCheckTest, self).setUp()
        self.test_good_matching = ('string.', 'string.', '')
        self.test_good_ignore = ('.', ' ', '')
        self.test_failure_1 = ('string.', 'string', '')
        self.test_failure_2 = ('string', 'string.', '')

    def test_japanese(self):
        self.do_test(False, ('Text:', 'Text。', ''), 'ja')
        self.do_test(True, ('Text:', 'Text', ''), 'ja')

    def test_hindi(self):
        self.do_test(False, ('Text.', 'Text।', ''), 'hi')
        self.do_test(True, ('Text.', 'Text', ''), 'hi')

    def test_armenian(self):
        self.do_test(False, ('Text:', 'Text`', ''), 'hy')
        self.do_test(False, ('Text:', 'Text՝', ''), 'hy')
        self.do_test(True, ('Text.', 'Text', ''), 'hy')


class EndColonCheckTest(CheckTestCase):
    check = EndColonCheck()

    def setUp(self):
        super(EndColonCheckTest, self).setUp()
        self.test_good_matching = ('string:', 'string:', '')
        self.test_failure_1 = ('string:', 'string', '')
        self.test_failure_2 = ('string', 'string:', '')

    def test_hy(self):
        self.do_test(False, ('Text:', 'Texte՝', ''), 'hy')
        self.do_test(True, ('Text:', 'Texte', ''), 'hy')
        self.do_test(False, ('Text', 'Texte:', ''), 'hy')

    def test_japanese(self):
        self.do_test(False, ('Text:', 'Texte。', ''), 'ja')

    def test_japanese_ignore(self):
        self.do_test(False, ('Text', 'Texte', ''), 'ja')

    def test_french_1(self):
        self.do_test(False, ('Text:', 'Texte : ', ''), 'fr')

    def test_french_2(self):
        self.do_test(False, ('Text:', 'Texte :', ''), 'fr')

    def test_french_ignore(self):
        self.do_test(False, ('Text', 'Texte', ''), 'fr')

    def test_french_wrong(self):
        self.do_test(True, ('Text:', 'Texte:', ''), 'fr')


class EndQuestionCheckTest(CheckTestCase):
    check = EndQuestionCheck()

    def setUp(self):
        super(EndQuestionCheckTest, self).setUp()
        self.test_good_matching = ('string?', 'string?', '')
        self.test_failure_1 = ('string?', 'string', '')
        self.test_failure_2 = ('string', 'string?', '')

    def test_hy(self):
        self.do_test(False, ('Text?', 'Texte՞', ''), 'hy')
        self.do_test(True, ('Text?', 'Texte', ''), 'hy')
        self.do_test(False, ('Text', 'Texte?', ''), 'hy')

    def test_french(self):
        self.do_test(False, ('Text?', 'Texte ?', ''), 'fr')
        self.do_test(False, ('Text?', 'Texte\u202F?', ''), 'fr')
        self.do_test(False, ('Text?', 'Texte&nbsp;?', ''), 'fr')

    def test_french_ignore(self):
        self.do_test(False, ('Text', 'Texte', ''), 'fr')

    def test_french_wrong(self):
        self.do_test(True, ('Text?', 'Texte?', ''), 'fr')

    def test_greek(self):
        self.do_test(False, ('Text?', 'Texte;', ''), 'el')
        self.do_test(False, ('Text?', 'Texte;', ''), 'el')

    def test_greek_ignore(self):
        self.do_test(False, ('Text', 'Texte', ''), 'el')

    def test_greek_wrong(self):
        self.do_test(True, ('Text?', 'Texte', ''), 'el')


class EndExclamationCheckTest(CheckTestCase):
    check = EndExclamationCheck()

    def setUp(self):
        super(EndExclamationCheckTest, self).setUp()
        self.test_good_matching = ('string!', 'string!', '')
        self.test_failure_1 = ('string!', 'string', '')
        self.test_failure_2 = ('string', 'string!', '')

    def test_hy(self):
        self.do_test(False, ('Text!', 'Texte՜', ''), 'hy')
        self.do_test(False, ('Text!', 'Texte', ''), 'hy')
        self.do_test(False, ('Text', 'Texte!', ''), 'hy')

    def test_eu(self):
        self.do_test(False, ('Text!', '¡Texte!', ''), 'eu')

    def test_french(self):
        self.do_test(False, ('Text!', 'Texte !', ''), 'fr')

    def test_french_ignore(self):
        self.do_test(False, ('Text', 'Texte', ''), 'fr')

    def test_french_wrong(self):
        self.do_test(True, ('Text!', 'Texte!', ''), 'fr')
        self.do_test(False, ('Text!', 'Texte !', ''), 'fr')


class EndEllipsisCheckTest(CheckTestCase):
    check = EndEllipsisCheck()

    def setUp(self):
        super(EndEllipsisCheckTest, self).setUp()
        self.test_good_matching = ('string…', 'string…', '')
        self.test_failure_1 = ('string…', 'string...', '')
        self.test_failure_2 = ('string.', 'string…', '')
        self.test_failure_3 = ('string..', 'string…', '')

    def test_translate(self):
        self.do_test(False, ('string...', 'string…', ''))


class NewlineCountingCheckTest(CheckTestCase):
    check = NewlineCountingCheck()

    def setUp(self):
        super(NewlineCountingCheckTest, self).setUp()
        self.test_good_matching = ('string\\nstring', 'string\\nstring', '')
        self.test_failure_1 = ('string\\nstring', 'string\\n\\nstring', '')
        self.test_failure_2 = ('string\\n\\nstring', 'string\\nstring', '')


class ZeroWidthSpaceCheckTest(CheckTestCase):
    check = ZeroWidthSpaceCheck()

    def setUp(self):
        super(ZeroWidthSpaceCheckTest, self).setUp()
        self.test_good_matching = ('str\u200bing', 'str\u200bing', '')
        self.test_failure_1 = ('str\u200bing', 'string', '')
        self.test_failure_2 = ('string', 'str\u200bing', '')


class MaxLengthCheckTest(TestCase):
    def setUp(self):
        self.check = MaxLengthCheck()
        self.test_good_matching = (
            'strings',
            'less than 21',
            'max-length:12'
        )
        self.test_good_matching_unicode = (
            'strings',
            'less than 21',
            'max-length:12'
        )

    def test_check(self):
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching[0]],
                [self.test_good_matching[1]],
                MockUnit(flags=(self.test_good_matching[2]))
            )
        )

    def test_unicode_check(self):
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching_unicode[0]],
                [self.test_good_matching_unicode[1]],
                MockUnit(flags=(self.test_good_matching_unicode[2]))
            )
        )

    def test_failure_check(self):
        self.assertTrue(
            self.check.check_target(
                [self.test_good_matching[0]],
                [self.test_good_matching[1]],
                MockUnit(flags=('max-length:10'))
            )
        )

    def test_failure_unicode_check(self):
        self.assertTrue(
            self.check.check_target(
                [self.test_good_matching_unicode[0]],
                [self.test_good_matching_unicode[1]],
                MockUnit(flags=('max-length:10'))
            )
        )

    def test_multiple_flags_check(self):
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching_unicode[0]],
                [self.test_good_matching_unicode[1]],
                MockUnit(flags=('max-length:3,max-length:12'))
            )
        )


class EndSemicolonCheckTest(CheckTestCase):
    check = EndSemicolonCheck()

    def setUp(self):
        super(EndSemicolonCheckTest, self).setUp()
        self.test_good_matching = ('string;', 'string;', '')
        self.test_failure_1 = ('string;', 'string', '')
        self.test_failure_2 = ('string:', 'string;', '')
        self.test_failure_3 = ('string', 'string;', '')

    def test_greek(self):
        self.do_test(False, ('Text?', 'Texte;', ''), 'el')
