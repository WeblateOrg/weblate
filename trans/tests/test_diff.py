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

from unittest import TestCase
from trans.simplediff import html_diff
from trans.templatetags.translations import fmtsourcediff, fmtsearchmatch
from trans.tests.test_checks import MockUnit


class DiffTest(TestCase):
    '''
    Testing of HTML diff function.
    '''
    def test_same(self):
        self.assertEqual(
            html_diff('first text', 'first text'),
            'first text'
        )

    def test_add(self):
        self.assertEqual(
            html_diff('first text', 'first new text'),
            'first <ins>new </ins>text'
        )

    def test_remove(self):
        self.assertEqual(
            html_diff('first old text', 'first text'),
            'first <del>old </del>text'
        )

    def test_replace(self):
        self.assertEqual(
            html_diff('first old text', 'first new text'),
            'first <del>old</del><ins>new</ins> text'
        )

    def test_fmtsourcediff(self):
        unit = MockUnit(source='Hello word!')
        self.assertEqual(
            fmtsourcediff('Hello world!', unit),
            u'<span lang="en" dir="ltr" class="direction">'
            'Hello wor<del>l</del>d!'
            '</span>'
        )

    def test_fmtsearchmatch(self):
        self.assertEqual(
            fmtsearchmatch('Hello world!', 'hello'),
            u'<span lang="en" dir="ltr" class="direction">'
            '<span class="hlmatch">Hello</span> world!'
            '</span>'
        )
