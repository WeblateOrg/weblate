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
Tests for language manipulations.
"""

from django.test import TestCase
from weblate.lang.models import Language, get_plural_type
from weblate.lang import data
from django.core.management import call_command
import os.path
import gettext


class LanguagesTest(TestCase):
    TEST_LANGUAGES = (
        (
            'cs_CZ',
            'cs',
            'ltr',
            '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
        ),
        (
            'czech',
            'cs',
            'ltr',
            '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
        ),
        (
            'cs_CZ@hantec',
            'cs_CZ@hantec',
            'ltr',
            '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
        ),
        (
            'de-DE',
            'de',
            'ltr',
            'n != 1',
        ),
        (
            'de_AT',
            'de_AT',
            'ltr',
            'n != 1',
        ),
        (
            'portuguese_portugal',
            'pt_PT',
            'ltr',
            'n > 1',
        ),
        (
            'pt-rBR',
            'pt_BR',
            'ltr',
            'n != 1',
        ),
        (
            'sr_RS@latin',
            'sr_RS@latin',
            'ltr',
            'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
            '(n%100<10 || n%100>=20) ? 1 : 2',
        ),
        (
            'sr-RS@latin',
            'sr_RS@latin',
            'ltr',
            'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
            '(n%100<10 || n%100>=20) ? 1 : 2',
        ),
        (
            'sr_RS_Latin',
            'sr_RS@latin',
            'ltr',
            'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
            '(n%100<10 || n%100>=20) ? 1 : 2',
        ),
        (
            'en_CA_MyVariant',
            'en_CA@myvariant',
            'ltr',
            'n != 1',
        ),
        (
            'en_CZ',
            'en_CZ',
            'ltr',
            'n != 1',
        ),
        (
            'zh_CN',
            'zh_CN',
            'ltr',
            '0',
        ),
        (
            'zh-CN',
            'zh_CN',
            'ltr',
            '0',
        ),
        (
            'zh-CN@test',
            'zh_CN@test',
            'ltr',
            '0',
        ),
        (
            'zh-rCN',
            'zh_CN',
            'ltr',
            '0',
        ),
        (
            'ar',
            'ar',
            'rtl',
            'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 '
            ': n%100>=11 ? 4 : 5',
        ),
        (
            'ar_AA',
            'ar',
            'rtl',
            'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 '
            ': n%100>=11 ? 4 : 5',
        ),
        (
            'ar_XX',
            'ar_XX',
            'rtl',
            'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 '
            ': n%100>=11 ? 4 : 5',
        ),
        (
            'xx',
            'xx',
            'ltr',
            'n != 1',
        ),
    )

    def test_auto_create(self):
        '''
        Tests that auto create correctly handles languages
        '''
        for original, expected, direction, plurals in self.TEST_LANGUAGES:
            # Create language
            lang = Language.objects.auto_get_or_create(original)
            # Check language code
            self.assertEqual(
                lang.code,
                expected,
                'Invalid code for %s: %s' % (original, lang.code)
            )
            # Check direction
            self.assertEqual(
                lang.direction,
                direction,
                'Invalid direction for %s' % original
            )
            # Check plurals
            self.assertEqual(
                lang.pluralequation,
                plurals,
                'Invalid plural for %s' % original
            )
            # Check whether html contains both language code and direction
            self.assertIn(direction, lang.get_html())
            self.assertIn(expected, lang.get_html())

    def test_plurals(self):
        '''
        Test whether plural form is correctly calculated.
        '''
        lang = Language.objects.get(code='cs')
        self.assertEqual(
            lang.get_plural_form(),
            'nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;'
        )


class CommandTest(TestCase):
    '''
    Tests for management commands.
    '''
    def test_setuplang(self):
        call_command('setuplang')
        self.assertTrue(Language.objects.exists())

    def test_setuplang_noupdate(self):
        call_command('setuplang', update=False)
        self.assertTrue(Language.objects.exists())

    def test_checklang(self):
        testfile = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'plurals.txt'
        )
        call_command('checklang', testfile)


class VerifyPluralsTest(TestCase):
    """
    In database plural form verification.
    """
    def test_valid(self):
        """Validates that we can name all plural equations"""
        for language in Language.objects.all():
            self.assertNotEqual(
                get_plural_type(
                    language.code,
                    language.pluralequation
                ),
                data.PLURAL_UNKNOWN
            )

    def test_equation(self):
        """Validates that all equations can be parsed by gettext"""
        # Verify we get an error on invalid syntax
        self.assertRaises(
            SyntaxError,
            gettext.c2py,
            'n==0 ? 1 2'
        )
        for language in Language.objects.all():
            # Validate plurals can be parsed
            plural = gettext.c2py(language.pluralequation)
            # Get maximal plural
            nplurals = max([plural(x) for x in range(200)]) + 1
            # Check it matches ours
            self.assertEquals(
                nplurals,
                language.nplurals,
                'Invalid nplurals for {0}: {1} ({2}, {3})'.format(
                    language.code,
                    nplurals,
                    language.nplurals,
                    language.pluralequation
                )
            )
