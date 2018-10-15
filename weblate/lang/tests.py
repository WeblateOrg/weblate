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

"""Test for language manipulations."""
from __future__ import unicode_literals

import gettext
from itertools import chain

from django.test import TestCase
from django.urls import reverse
from django.core.management import call_command
from django.utils.encoding import force_text
from django.utils.translation import activate

from six import StringIO, PY2, with_metaclass

from weblate.lang.models import Language, Plural, get_plural_type
from weblate.lang import data
from weblate.langdata import languages
from weblate.trans.tests.test_models import BaseTestCase
from weblate.trans.tests.test_views import FixtureTestCase


LANGUAGES = (
    (
        'cs_CZ',
        'cs',
        'ltr',
        '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
        'Czech',
        False,
    ),
    (
        'cs (2)',
        'cs',
        'ltr',
        '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
        'Czech',
        False,
    ),
    (
        'czech',
        'cs',
        'ltr',
        '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
        'Czech',
        False,
    ),
    (
        'cs_CZ@hantec',
        'cs_CZ@hantec',
        'ltr',
        '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
        'Czech (cs_CZ@hantec)',
        True,
    ),
    (
        'de-DE',
        'de',
        'ltr',
        'n != 1',
        'German',
        False,
    ),
    (
        'de_AT',
        'de_AT',
        'ltr',
        'n != 1',
        'Austrian German',
        False,
    ),
    (
        'de_CZ',
        'de_CZ',
        'ltr',
        'n != 1',
        'German (de_CZ)',
        True,
    ),
    (
        'portuguese_portugal',
        'pt_PT',
        'ltr',
        'n > 1',
        'Portuguese (Portugal)',
        False,
    ),
    (
        'pt-rBR',
        'pt_BR',
        'ltr',
        'n > 1',
        'Portuguese (Brazil)',
        False,
    ),
    (
        'sr+latn',
        'sr_Latn',
        'ltr',
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
        'Serbian (latin)',
        False,
    ),
    (
        'sr_RS@latin',
        'sr_Latn',
        'ltr',
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
        'Serbian (latin)',
        False,
    ),
    (
        'sr-RS@latin',
        'sr_Latn',
        'ltr',
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
        'Serbian (latin)',
        False,
    ),
    (
        'sr_RS@latin',
        'sr_Latn',
        'ltr',
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
        'Serbian (latin)',
        False,
    ),
    (
        'en_CA_MyVariant',
        'en_CA@myvariant',
        'ltr',
        'n != 1',
        'English (Canada)',
        True,
    ),
    (
        'en_CZ',
        'en_CZ',
        'ltr',
        'n != 1',
        'English (en_CZ)',
        True,
    ),
    (
        'zh_CN',
        'zh_Hans',
        'ltr',
        '0',
        'Chinese (Simplified)',
        False,
    ),
    (
        'zh-CN',
        'zh_Hans',
        'ltr',
        '0',
        'Chinese (Simplified)',
        False,
    ),
    (
        'zh_HANT',
        'zh_Hant',
        'ltr',
        '0',
        'Chinese (Traditional)',
        False,
    ),
    (
        'zh-HANT',
        'zh_Hant',
        'ltr',
        '0',
        'Chinese (Traditional)',
        False,
    ),
    (
        'zh-CN@test',
        'zh_CN@test',
        'ltr',
        '0',
        'Chinese (Simplified)',
        True,
    ),
    (
        'zh-rCN',
        'zh_Hans',
        'ltr',
        '0',
        'Chinese (Simplified)',
        False,
    ),
    (
        'zh_rCN',
        'zh_Hans',
        'ltr',
        '0',
        'Chinese (Simplified)',
        False,
    ),
    (
        'zh_HK',
        'zh_Hant_HK',
        'ltr',
        '0',
        'Chinese (Hong Kong)',
        False,
    ),
    (
        'zh_Hant-rHK',
        'zh_Hant_HK',
        'ltr',
        '0',
        'Chinese (Hong Kong)',
        False,
    ),
    (
        'ar',
        'ar',
        'rtl',
        'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 '
        ': n%100>=11 ? 4 : 5',
        'Arabic',
        False,
    ),
    (
        'ar_AA',
        'ar',
        'rtl',
        'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 '
        ': n%100>=11 ? 4 : 5',
        'Arabic',
        False,
    ),
    (
        'ar_XX',
        'ar_XX',
        'rtl',
        'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 '
        ': n%100>=11 ? 4 : 5',
        'Arabic (ar_XX)',
        True,
    ),
    (
        'xx',
        'xx',
        'ltr',
        'n != 1',
        'xx (generated)',
        True,
    ),
    (
        'nb_NO',
        'nb_NO',
        'ltr',
        'n != 1',
        'Norwegian Bokmål',
        False,
    ),
    (
        'nb-NO',
        'nb_NO',
        'ltr',
        'n != 1',
        'Norwegian Bokmål',
        False,
    ),
    (
        'nb',
        'nb_NO',
        'ltr',
        'n != 1',
        'Norwegian Bokmål',
        False,
    ),
)


class TestSequenceMeta(type):
    def __new__(mcs, name, bases, dict):

        def gen_test(original, expected, direction, plural, name, create):
            def test(self):
                self.run_create(
                    original, expected, direction, plural, name, create
                )
            return test

        for params in LANGUAGES:
            test_name = "test_create_%s" % params[1].replace('@', '_')
            dict[test_name] = gen_test(*params)

        return type.__new__(mcs, name, bases, dict)


class LanguagesTest(with_metaclass(TestSequenceMeta, BaseTestCase)):
    def setUp(self):
        # Ensure we're using English
        activate('en')

    def run_create(self, original, expected, direction, plural, name, create):
        """Test that auto create correctly handles languages"""
        # Lookup language
        lang = Language.objects.auto_get_or_create(original, create=False)
        self.assertEqual(
            create,
            not bool(lang.pk),
            'Failed to assert creation for {}: {}'.format(
                original, create
            )
        )
        # Create language
        lang = Language.objects.auto_get_or_create(original)
        # Check language code
        self.assertEqual(
            lang.code,
            expected,
            'Invalid code for {0}: {1}'.format(original, lang.code)
        )
        # Check direction
        self.assertEqual(
            lang.direction,
            direction,
            'Invalid direction for {0}'.format(original)
        )
        # Check plurals
        plural_obj = lang.plural_set.get(source=Plural.SOURCE_DEFAULT)
        self.assertEqual(
            plural_obj.equation,
            plural,
            'Invalid plural for {0} (expected {1}, got {2})'.format(
                original, plural, plural_obj.equation,
            )
        )
        # Check whether html contains both language code and direction
        self.assertIn(direction, lang.get_html())
        self.assertIn(expected, lang.get_html())
        # Check name
        self.assertEqual(force_text(lang), name)


class CommandTest(TestCase):
    """Test for management commands."""
    def test_setuplang(self):
        call_command('setuplang')
        self.assertTrue(Language.objects.exists())

    def test_setuplang_noupdate(self):
        call_command('setuplang', update=False)
        self.assertTrue(Language.objects.exists())

    def check_list(self, **kwargs):
        output = StringIO()
        call_command(
            'list_languages', 'cs',
            stdout=output,
            **kwargs
        )
        if PY2:
            self.assertIn(b'Czech', output.getvalue())
        else:
            self.assertIn('Czech', output.getvalue())

    def test_list_languages(self):
        self.check_list()

    def test_list_languages_lower(self):
        self.check_list(lower=True)

    def test_move_language(self):
        Language.objects.auto_create('cs_CZ')
        call_command('move_language', 'cs_CZ', 'cs')


class VerifyPluralsTest(TestCase):
    """In database plural form verification."""
    @staticmethod
    def all_data():
        return chain(languages.LANGUAGES, languages.EXTRAPLURALS)

    def test_valid(self):
        """Validate that we can name all plural equations"""
        for code, dummy, dummy, pluraleq in self.all_data():
            self.assertNotEqual(
                get_plural_type(
                    code.replace('_', '-').split('-')[0],
                    pluraleq
                ),
                data.PLURAL_UNKNOWN,
                'Can not guess plural type for {0} ({1})'.format(
                    code, pluraleq
                )
            )

    def test_equation(self):
        """Validate that all equations can be parsed by gettext"""
        # Verify we get an error on invalid syntax
        self.assertRaises(
            (SyntaxError, ValueError),
            gettext.c2py,
            'n==0 ? 1 2'
        )
        for code, dummy, nplurals, pluraleq in self.all_data():
            # Validate plurals can be parsed
            plural = gettext.c2py(pluraleq)
            # Get maximal plural
            calculated = max([plural(x) for x in range(200)]) + 1
            # Check it matches ours
            self.assertEqual(
                calculated,
                nplurals,
                'Invalid nplurals for {0}: {1} ({2}, {3})'.format(
                    code,
                    calculated,
                    nplurals,
                    pluraleq,
                )
            )


class LanguagesViewTest(FixtureTestCase):
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

    def test_language_br(self):
        response = self.client.get(reverse(
            'show_language',
            kwargs={'lang': 'br'}
        ))
        self.assertContains(response, 'Breton')
        # Example is listed
        self.assertContains(response, '1000000')

    def test_project_language(self):
        response = self.client.get(reverse(
            'project-language',
            kwargs={'lang': 'cs', 'project': 'test'}
        ))
        self.assertContains(response, 'Czech')
        self.assertContains(response, '/projects/test/test/cs/')

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


class PluralsCompareTest(TestCase):
    def test_match(self):
        plural = Plural.objects.get(
            language__code='cs', source=Plural.SOURCE_DEFAULT
        )
        self.assertTrue(
            plural.same_plural(plural.number, plural.equation)
        )

    def test_formula(self):
        plural = Plural.objects.get(
            language__code='pt', source=Plural.SOURCE_DEFAULT
        )
        self.assertFalse(
            plural.same_plural(2, '(n != 1)')
        )

    def test_different_formula(self):
        plural = Plural.objects.get(
            language__code='pt', source=Plural.SOURCE_DEFAULT
        )
        self.assertTrue(
            plural.same_plural(2, '(n > 1)')
        )

    def test_different_count(self):
        plural = Plural.objects.get(
            language__code='lt', source=Plural.SOURCE_DEFAULT
        )
        self.assertFalse(
            plural.same_plural(
                4, '(n%10==1 ? 0 : n%10==1 && n%100!=11 ?'
                ' 1 : n %10>=2 && (n%100<10 || n%100>=20) ? 2 : 3)'
            )
        )

    def test_invalid(self):
        plural = Plural.objects.get(
            language__code='lt', source=Plural.SOURCE_DEFAULT
        )
        self.assertFalse(
            plural.same_plural(1, 'bogus')
        )


class PluralTest(TestCase):
    def test_examples(self):
        plural = Plural(number=2, equation='n!=1')
        self.assertEqual(
            plural.examples,
            {0: ['1'], 1: ['0', '2', '3', '4', '5', '6', '7', '8', '9', '10']}
        )

    def test_plurals(self):
        """Test whether plural form is correctly calculated."""
        plural = Plural.objects.get(language__code='cs')
        self.assertEqual(
            plural.plural_form,
            'nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;'
        )

    def test_plural_names(self):
        plural = Plural.objects.get(language__code='cs')
        self.assertEqual(plural.get_plural_name(0), 'One')
        self.assertEqual(plural.get_plural_name(1), 'Few')
        self.assertEqual(plural.get_plural_name(2), 'Other')

    def test_plural_names_invalid(self):
        plural = Plural.objects.get(language__code='cs')
        plural.type = -1
        self.assertEqual(plural.get_plural_name(0), 'Singular')
        self.assertEqual(plural.get_plural_name(1), 'Plural')
        self.assertEqual(plural.get_plural_name(2), 'Plural form 2')

    def test_plural_labels(self):
        plural = Plural.objects.get(language__code='cs')
        label = plural.get_plural_label(0)
        self.assertIn('One', label)
        self.assertIn('1', label)
        label = plural.get_plural_label(1)
        self.assertIn('Few', label)
        self.assertIn('2, 3, 4', label)
        label = plural.get_plural_label(2)
        self.assertIn('Other', label)
        self.assertIn('5, 6, 7', label)

    def test_plural_type(self):
        language = Language.objects.get(code='cs')
        plural = Plural.objects.create(
            language=language,
            number=3,
            equation=(
                '(n%10==1 && n%100!=11 ? 0 : '
                'n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'
            ),
            source=Plural.SOURCE_GETTEXT,
        )
        self.assertEqual(plural.type, data.PLURAL_ONE_FEW_OTHER)
