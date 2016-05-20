# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
Tests for language manipulations.
"""

import os.path
import gettext
from django.test import TestCase
from django.core.urlresolvers import reverse
from django.core.management import call_command
from django.utils.encoding import force_text
from weblate.lang.models import Language, get_plural_type
from weblate.lang import data
from weblate.trans.tests.test_views import ViewTestCase


class LanguagesTest(TestCase):
    TEST_LANGUAGES = (
        (
            'cs_CZ',
            'cs',
            'ltr',
            '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
            'Czech',
        ),
        (
            'cs (2)',
            'cs',
            'ltr',
            '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
            'Czech',
        ),
        (
            'czech',
            'cs',
            'ltr',
            '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
            'Czech',
        ),
        (
            'cs_CZ@hantec',
            'cs_CZ@hantec',
            'ltr',
            '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
            'Czech (cs_CZ@hantec)',
        ),
        (
            'de-DE',
            'de',
            'ltr',
            'n != 1',
            'German',
        ),
        (
            'de_AT',
            'de_AT',
            'ltr',
            'n != 1',
            'Austrian German',
        ),
        (
            'de_CZ',
            'de_CZ',
            'ltr',
            'n != 1',
            'German (de_CZ)',
        ),
        (
            'portuguese_portugal',
            'pt_PT',
            'ltr',
            'n > 1',
            'Portuguese (Portugal)',
        ),
        (
            'pt-rBR',
            'pt_BR',
            'ltr',
            'n > 1',
            'Portuguese (Brazil)',
        ),
        (
            'sr_RS@latin',
            'sr_Latn',
            'ltr',
            'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
            '(n%100<10 || n%100>=20) ? 1 : 2',
            'Serbian (latin)',
        ),
        (
            'sr-RS@latin',
            'sr_Latn',
            'ltr',
            'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
            '(n%100<10 || n%100>=20) ? 1 : 2',
            'Serbian (latin)',
        ),
        (
            'sr_RS@latin',
            'sr_Latn',
            'ltr',
            'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
            '(n%100<10 || n%100>=20) ? 1 : 2',
            'Serbian (latin)',
        ),
        (
            'en_CA_MyVariant',
            'en_CA@myvariant',
            'ltr',
            'n != 1',
            'English (Canada)',
        ),
        (
            'en_CZ',
            'en_CZ',
            'ltr',
            'n != 1',
            'English (en_CZ)',
        ),
        (
            'zh_CN',
            'zh_Hans',
            'ltr',
            '0',
            'Simplified Chinese',
        ),
        (
            'zh-CN',
            'zh_Hans',
            'ltr',
            '0',
            'Simplified Chinese',
        ),
        (
            'zh-CN@test',
            'zh_CN@test',
            'ltr',
            '0',
            'Chinese (zh_CN@test)',
        ),
        (
            'zh-rCN',
            'zh_Hans',
            'ltr',
            '0',
            'Simplified Chinese',
        ),
        (
            'ar',
            'ar',
            'rtl',
            'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 '
            ': n%100>=11 ? 4 : 5',
            'Arabic',
        ),
        (
            'ar_AA',
            'ar',
            'rtl',
            'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 '
            ': n%100>=11 ? 4 : 5',
            'Arabic',
        ),
        (
            'ar_XX',
            'ar_XX',
            'rtl',
            'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 '
            ': n%100>=11 ? 4 : 5',
            'Arabic (ar_XX)',
        ),
        (
            'xx',
            'xx',
            'ltr',
            'n != 1',
            'xx (generated)',
        ),
    )

    def test_auto_create(self):
        '''
        Tests that auto create correctly handles languages
        '''
        for original, expected, direction, plural, name in self.TEST_LANGUAGES:
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
                plural,
                'Invalid plural for {0} (expected {1}, got {2})'.format(
                    original, plural, lang.pluralequation,
                )
            )
            # Check whether html contains both language code and direction
            self.assertIn(direction, lang.get_html())
            self.assertIn(expected, lang.get_html())
            # Check name
            self.assertEqual(force_text(lang), name)

    def test_plurals(self):
        '''
        Test whether plural form is correctly calculated.
        '''
        lang = Language.objects.get(code='cs')
        self.assertEqual(
            lang.get_plural_form(),
            'nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;'
        )

    def test_plural_labels(self):
        lang = Language.objects.get(code='cs')
        self.assertEqual(lang.get_plural_label(0), 'One')
        self.assertEqual(lang.get_plural_label(1), 'Few')
        self.assertEqual(lang.get_plural_label(2), 'Other')

    def test_plural_labels_invalid(self):
        lang = Language.objects.get(code='cs')
        lang.plural_type = -1
        self.assertEqual(lang.get_plural_label(0), 'Singular')
        self.assertEqual(lang.get_plural_label(1), 'Plural')
        self.assertEqual(lang.get_plural_label(2), 'Plural form 2')


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
                data.PLURAL_UNKNOWN,
                'Can not guess plural type for {0} ({1})'.format(
                    language.code,
                    language.pluralequation
                )
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
            self.assertEqual(
                nplurals,
                language.nplurals,
                'Invalid nplurals for {0}: {1} ({2}, {3})'.format(
                    language.code,
                    nplurals,
                    language.nplurals,
                    language.pluralequation
                )
            )


class LanguagesViewTest(ViewTestCase):
    def test_languages(self):
        response = self.client.get(reverse('languages'))
        self.assertContains(response, 'Czech')

    def test_language(self):
        response = self.client.get(reverse(
            'show_language',
            kwargs={'lang': 'cs'}
        ))
        self.assertContains(response, 'Czech')
        self.assertContains(response, 'Test/Test')

    def test_language_redirect(self):
        response = self.client.get(reverse(
            'show_language',
            kwargs={'lang': 'cs_CZ'}
        ))
        self.assertRedirects(
            response,
            reverse(
                'show_language',
                kwargs={'lang': 'cs'}
            )
        )

    def test_language_nonexisting(self):
        response = self.client.get(reverse(
            'show_language',
            kwargs={'lang': 'nonexisting'}
        ))
        self.assertEqual(response.status_code, 404)
