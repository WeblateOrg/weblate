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

from weblate.trans.checks.chars import (
    BeginNewlineCheck, EndNewlineCheck,
    BeginSpaceCheck, EndSpaceCheck,
    EndStopCheck, EndColonCheck,
    EndQuestionCheck, EndExclamationCheck,
    EndEllipsisCheck,
    NewlineCountingCheck,
    ZeroWidthSpaceCheck,
)
from weblate.trans.tests.test_checks import CheckTestCase


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
        self.do_test(False, ('Text!', u'Texte !', ''), 'fr')
        self.do_test(True, ('Text', u'Texte ', ''), 'fr')


class EndStopCheckTest(CheckTestCase):
    check = EndStopCheck()

    def setUp(self):
        super(EndStopCheckTest, self).setUp()
        self.test_good_matching = ('string.', 'string.', '')
        self.test_good_ignore = ('.', ' ', '')
        self.test_failure_1 = ('string.', 'string', '')
        self.test_failure_2 = ('string', 'string.', '')

    def test_japanese(self):
        self.do_test(False, ('Text:', u'Text。', ''), 'ja')
        self.do_test(True, ('Text:', u'Text', ''), 'ja')

    def test_hindi(self):
        self.do_test(False, ('Text.', u'Text।', ''), 'hi')
        self.do_test(True, ('Text.', u'Text', ''), 'hi')


class EndColonCheckTest(CheckTestCase):
    check = EndColonCheck()

    def setUp(self):
        super(EndColonCheckTest, self).setUp()
        self.test_good_matching = ('string:', 'string:', '')
        self.test_failure_1 = ('string:', 'string', '')
        self.test_failure_2 = ('string', 'string:', '')

    def test_hy(self):
        self.do_test(False, ('Text:', u'Texte՝', ''), 'hy')
        self.do_test(True, ('Text:', u'Texte', ''), 'hy')
        self.do_test(False, ('Text', u'Texte:', ''), 'hy')

    def test_japanese(self):
        self.do_test(False, ('Text:', u'Texte。', ''), 'ja')

    def test_japanese_ignore(self):
        self.do_test(False, ('Text', u'Texte', ''), 'ja')

    def test_french_1(self):
        self.do_test(False, ('Text:', u'Texte : ', ''), 'fr')

    def test_french_2(self):
        self.do_test(False, ('Text:', u'Texte :', ''), 'fr')

    def test_french_ignore(self):
        self.do_test(False, ('Text', u'Texte', ''), 'fr')

    def test_french_wrong(self):
        self.do_test(True, ('Text:', u'Texte:', ''), 'fr')


class EndQuestionCheckTest(CheckTestCase):
    check = EndQuestionCheck()

    def setUp(self):
        super(EndQuestionCheckTest, self).setUp()
        self.test_good_matching = ('string?', 'string?', '')
        self.test_failure_1 = ('string?', 'string', '')
        self.test_failure_2 = ('string', 'string?', '')

    def test_hy(self):
        self.do_test(False, ('Text?', u'Texte՞', ''), 'hy')
        self.do_test(True, ('Text?', u'Texte', ''), 'hy')
        self.do_test(False, ('Text', u'Texte?', ''), 'hy')

    def test_french(self):
        self.do_test(False, ('Text?', u'Texte ?', ''), 'fr')

    def test_french_ignore(self):
        self.do_test(False, ('Text', u'Texte', ''), 'fr')

    def test_french_wrong(self):
        self.do_test(True, ('Text?', u'Texte?', ''), 'fr')

    def test_greek(self):
        self.do_test(False, ('Text?', u'Texte;', ''), 'el')

    def test_greek_ignore(self):
        self.do_test(False, ('Text', u'Texte', ''), 'el')

    def test_greek_wrong(self):
        self.do_test(True, ('Text?', u'Texte', ''), 'el')


class EndExclamationCheckTest(CheckTestCase):
    check = EndExclamationCheck()

    def setUp(self):
        super(EndExclamationCheckTest, self).setUp()
        self.test_good_matching = ('string!', 'string!', '')
        self.test_failure_1 = ('string!', 'string', '')
        self.test_failure_2 = ('string', 'string!', '')

    def test_hy(self):
        self.do_test(False, ('Text!', u'Texte՜', ''), 'hy')
        self.do_test(False, ('Text!', u'Texte', ''), 'hy')
        self.do_test(False, ('Text', u'Texte!', ''), 'hy')

    def test_eu(self):
        self.do_test(False, ('Text!', u'¡Texte!', ''), 'eu')

    def test_french(self):
        self.do_test(False, ('Text!', u'Texte !', ''), 'fr')

    def test_french_ignore(self):
        self.do_test(False, ('Text', u'Texte', ''), 'fr')

    def test_french_wrong(self):
        self.do_test(True, ('Text!', u'Texte!', ''), 'fr')


class EndEllipsisCheckTest(CheckTestCase):
    check = EndEllipsisCheck()

    def setUp(self):
        super(EndEllipsisCheckTest, self).setUp()
        self.test_good_matching = (u'string…', u'string…', '')
        self.test_failure_1 = (u'string…', 'string...', '')
        self.test_failure_2 = ('string.', u'string…', '')
        self.test_failure_3 = ('string..', u'string…', '')

    def test_translate(self):
        self.do_test(False, ('string...', u'string…', ''))


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
        self.test_good_matching = (u'str\u200bing', u'str\u200bing', '')
        self.test_failure_1 = (u'str\u200bing', 'string', '')
        self.test_failure_2 = ('string', u'str\u200bing', '')
