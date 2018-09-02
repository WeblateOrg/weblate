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

"""Test for import and export."""

from __future__ import unicode_literals

from django.contrib.messages import ERROR
from django.test import SimpleTestCase
from django.urls import reverse

from weblate.trans.forms import SimpleUploadForm
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file

TEST_PO = get_test_file('cs.po')
TEST_CSV = get_test_file('cs.csv')
TEST_CSV_QUOTES = get_test_file('cs-quotes.csv')
TEST_CSV_QUOTES_ESCAPED = get_test_file('cs-quotes-escaped.csv')
TEST_PO_BOM = get_test_file('cs-bom.po')
TEST_FUZZY_PO = get_test_file('cs-fuzzy.po')
TEST_BADPLURALS = get_test_file('cs-badplurals.po')
TEST_MO = get_test_file('cs.mo')
TEST_XLIFF = get_test_file('cs.poxliff')
TEST_ANDROID = get_test_file('strings-cs.xml')
TEST_XLSX = get_test_file('cs.xlsx')

TRANSLATION_OURS = 'Nazdar světe!\n'
TRANSLATION_PO = 'Ahoj světe!\n'


class ImportBaseTest(ViewTestCase):
    """Base test of file imports."""
    test_file = TEST_PO

    def setUp(self):
        super(ImportBaseTest, self).setUp()
        # We need extra privileges for overwriting
        self.user.is_superuser = True
        self.user.save()

    def do_import(self, test_file=None, follow=False, **kwargs):
        """Helper to perform file import."""
        if test_file is None:
            test_file = self.test_file

        with open(test_file, 'rb') as handle:
            params = {'file': handle, 'method': 'translate'}
            params.update(kwargs)
            return self.client.post(
                reverse(
                    'upload_translation',
                    kwargs=self.kw_translation
                ),
                params,
                follow=follow
            )


class ImportTest(ImportBaseTest):
    """Testing of file imports."""
    test_file = TEST_PO

    def test_import_normal(self):
        """Test importing normally."""
        response = self.do_import()
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 1)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, TRANSLATION_PO)

    def test_import_author(self):
        """Test importing normally."""
        response = self.do_import(
            author_name='Testing User',
            author_email='noreply@weblate.org'
        )
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 1)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, TRANSLATION_PO)

    def test_import_overwrite(self):
        """Test importing with overwriting."""
        # Translate one unit
        self.change_unit(TRANSLATION_OURS)

        response = self.do_import(upload_overwrite='yes')
        self.assertRedirects(response, self.translation_url)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, TRANSLATION_PO)

    def test_import_no_overwrite(self):
        """Test importing without overwriting."""
        # Translate one unit
        self.change_unit(TRANSLATION_OURS)

        response = self.do_import()
        self.assertRedirects(response, self.translation_url)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, TRANSLATION_OURS)

    def test_import_fuzzy(self):
        """Test importing as fuzzy."""
        response = self.do_import(method='fuzzy')
        self.assertRedirects(response, self.translation_url)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, TRANSLATION_PO)
        self.assertEqual(unit.fuzzy, True)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 1)
        self.assertEqual(translation.stats.all, 4)

    def test_import_suggest(self):
        """Test importing as suggestion."""
        response = self.do_import(method='suggest')
        self.assertRedirects(response, self.translation_url)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.translated, False)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)
        self.assertEqual(
            translation.stats.suggestions,
            1
        )

    def test_import_xliff(self):
        response = self.do_import(test_file=TEST_XLIFF, follow=True)
        self.assertContains(response, 'updated: 1')
        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 1)


class ImportErrorTest(ImportBaseTest):
    """Testing import of broken files."""
    def test_mismatched_plurals(self):
        """Test importing a file with different number of plural forms.

        In response to issue #900
        """
        response = self.do_import(test_file=TEST_BADPLURALS, follow=True)
        self.assertRedirects(response, self.translation_url)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level, ERROR)
        self.assertIn("Plural forms do not match", messages[0].message)


class BOMImportTest(ImportTest):
    test_file = TEST_PO_BOM


class XliffImportTest(ImportTest):
    test_file = TEST_XLIFF


class ImportFuzzyTest(ImportBaseTest):
    """Testing of fuzzy file imports."""
    test_file = TEST_FUZZY_PO

    def test_import_normal(self):
        """Test importing normally."""
        response = self.do_import(
            fuzzy=''
        )
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)

    def test_import_process(self):
        """Test importing including fuzzy strings."""
        response = self.do_import(
            fuzzy='process'
        )
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 1)
        self.assertEqual(translation.stats.all, 4)

    def test_import_approve(self):
        """Test importing ignoring fuzzy flag."""
        response = self.do_import(
            fuzzy='approve'
        )
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 1)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)

    def test_import_review(self):
        """Test importing as approved."""
        self.project.enable_review = True
        self.project.save()
        response = self.do_import(method='approve', fuzzy='approve')
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.approved, 1)
        self.assertEqual(translation.stats.translated, 1)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)


class ImportMoTest(ImportTest):
    """Testing of mo file imports."""
    test_file = TEST_MO


class ImportMoPoTest(ImportTest):
    """Testing of mo file imports."""
    test_file = TEST_MO

    def create_component(self):
        return self.create_po()


class ImportJoomlaTest(ImportTest):
    def create_component(self):
        return self.create_joomla()


class ImportJSONTest(ImportTest):
    def create_component(self):
        return self.create_json()


class ImportJSONMonoTest(ImportTest):
    def create_component(self):
        return self.create_json_mono()


class ImportPHPMonoTest(ImportTest):
    def create_component(self):
        return self.create_php_mono()


class StringsImportTest(ImportTest):
    def create_component(self):
        return self.create_iphone()


class AndroidImportTest(ViewTestCase):
    def create_component(self):
        return self.create_android()

    def test_import(self):
        with open(TEST_ANDROID, 'rb') as handle:
            self.client.post(
                reverse(
                    'upload_translation',
                    kwargs=self.kw_translation
                ),
                {'file': handle, 'method': 'translate'}
            )
        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 2)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)


class CSVImportTest(ViewTestCase):
    test_file = TEST_CSV

    def test_import(self):
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        with open(self.test_file, 'rb') as handle:
            self.client.post(
                reverse(
                    'upload_translation',
                    kwargs=self.kw_translation
                ),
                {'file': handle, 'method': 'translate'}
            )
        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 1)
        self.assertEqual(translation.stats.fuzzy, 0)


class CSVQuotesImportTest(CSVImportTest):
    test_file = TEST_CSV_QUOTES


class CSVQuotesEscapedImportTest(CSVImportTest):
    test_file = TEST_CSV_QUOTES_ESCAPED


class XlsxImportTest(CSVImportTest):
    test_file = TEST_XLSX


class ExportTest(ViewTestCase):
    """Testing of file export."""
    def create_component(self):
        # Needs to create PO file to have language pack option
        return self.create_po()

    def setUp(self):
        super(ExportTest, self).setUp()
        # Add some content so that .mo files is non empty
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )

    def test_export(self):
        response = self.client.get(
            reverse(
                'download_translation',
                kwargs=self.kw_translation
            )
        )
        self.assertContains(response, 'Weblate Hello World 2016')
        self.assertContains(response, 'Nazdar svete!')
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename=test-test-cs.po'
        )

    def export_format(self, fmt, **extra):
        extra['format'] = fmt
        return self.client.get(
            reverse(
                'download_translation',
                kwargs=self.kw_translation,
            ),
            extra
        )

    def test_export_po(self):
        response = self.export_format('po')
        self.assertContains(
            response, 'Orangutan has %d bananas'
        )
        self.assertContains(
            response, '/projects/test/test/cs/'
        )

    def test_export_po_todo(self):
        response = self.export_format('po', type='todo')
        self.assertContains(
            response, 'Orangutan has %d bananas'
        )
        self.assertContains(
            response, '/projects/test/test/cs/'
        )

    def test_export_tmx(self):
        response = self.export_format('tmx')
        self.assertContains(
            response, 'Orangutan has %d banana'
        )

    def test_export_xliff(self):
        response = self.export_format('xliff')
        self.assertContains(
            response, 'Orangutan has %d banana'
        )

    def test_export_xliff11(self):
        response = self.export_format('xliff11')
        self.assertContains(
            response, 'urn:oasis:names:tc:xliff:document:1.1'
        )
        self.assertContains(
            response, 'Orangutan has %d banana'
        )

    def test_export_xlsx(self):
        response = self.export_format('xlsx')
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename=test-test-cs.xlsx'
        )
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            '; charset=utf-8'
        )

    def test_export_invalid(self):
        response = self.export_format('invalid')
        self.assertEqual(response.status_code, 302)


class FormTest(SimpleTestCase):
    def test_remove(self):
        form = SimpleUploadForm()
        form.remove_translation_choice('suggest')
        self.assertEqual(
            [x[0] for x in form.fields['method'].choices],
            ['translate', 'approve', 'fuzzy']
        )
