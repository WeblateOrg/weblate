#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


from copy import copy

from django.contrib.messages import ERROR
from django.test import SimpleTestCase
from django.urls import reverse

from weblate.trans.forms import SimpleUploadForm
from weblate.trans.models import ComponentList
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file

TEST_PO = get_test_file("cs.po")
TEST_CSV = get_test_file("cs.csv")
TEST_CSV_QUOTES = get_test_file("cs-quotes.csv")
TEST_CSV_QUOTES_ESCAPED = get_test_file("cs-quotes-escaped.csv")
TEST_PO_BOM = get_test_file("cs-bom.po")
TEST_FUZZY_PO = get_test_file("cs-fuzzy.po")
TEST_BADPLURALS = get_test_file("cs-badplurals.po")
TEST_POT = get_test_file("hello.pot")
TEST_POT_CHARSET = get_test_file("hello-charset.pot")
TEST_MO = get_test_file("cs.mo")
TEST_XLIFF = get_test_file("cs.poxliff")
TEST_ANDROID = get_test_file("strings-cs.xml")
TEST_XLSX = get_test_file("cs.xlsx")
TEST_TBX = get_test_file("terms.tbx")

TRANSLATION_OURS = "Nazdar světe!\n"
TRANSLATION_PO = "Ahoj světe!\n"


class ImportBaseTest(ViewTestCase):
    """Base test of file imports."""

    test_file = TEST_PO

    def setUp(self):
        super().setUp()
        # We need extra privileges for overwriting
        self.user.is_superuser = True
        self.user.save()

    def do_import(self, test_file=None, follow=False, **kwargs):
        """Helper to perform file import."""
        if test_file is None:
            test_file = self.test_file

        with open(test_file, "rb") as handle:
            params = {
                "file": handle,
                "method": "translate",
                "author_name": self.user.full_name,
                "author_email": self.user.email,
            }
            params.update(kwargs)
            return self.client.post(
                reverse("upload_translation", kwargs=self.kw_translation),
                params,
                follow=follow,
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
            author_name="Testing User", author_email="john@example.com"
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

        response = self.do_import(conflicts="replace-translated")
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
        response = self.do_import(method="fuzzy")
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
        response = self.do_import(method="suggest")
        self.assertRedirects(response, self.translation_url)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.translated, False)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)
        self.assertEqual(translation.stats.suggestions, 1)

    def test_import_xliff(self):
        response = self.do_import(test_file=TEST_XLIFF, follow=True)
        self.assertContains(response, "updated: 1")
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
        self.assertIn(
            "Plural forms in the uploaded file do not match", messages[0].message
        )


class BOMImportTest(ImportTest):
    test_file = TEST_PO_BOM


class XliffImportTest(ImportTest):
    test_file = TEST_XLIFF


class ImportFuzzyTest(ImportBaseTest):
    """Testing of fuzzy file imports."""

    test_file = TEST_FUZZY_PO

    def test_import_normal(self):
        """Test importing normally."""
        response = self.do_import(fuzzy="")
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)

    def test_import_process(self):
        """Test importing including fuzzy strings."""
        response = self.do_import(fuzzy="process")
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 1)
        self.assertEqual(translation.stats.all, 4)

    def test_import_approve(self):
        """Test importing ignoring fuzzy flag."""
        response = self.do_import(fuzzy="approve")
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 1)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)

    def test_import_review(self):
        """Test importing as approved."""
        self.project.translation_review = True
        self.project.save()
        response = self.do_import(method="approve", fuzzy="approve")
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
        with open(TEST_ANDROID, "rb") as handle:
            self.client.post(
                reverse("upload_translation", kwargs=self.kw_translation),
                {
                    "file": handle,
                    "method": "translate",
                    "author_name": self.user.full_name,
                    "author_email": self.user.email,
                },
            )
        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 2)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)

    def test_replace(self):
        self.user.is_superuser = True
        self.user.save()
        kwargs = copy(self.kw_translation)
        kwargs["lang"] = "en"
        with open(TEST_ANDROID, "rb") as handle:
            self.client.post(
                reverse("upload_translation", kwargs=kwargs),
                {
                    "file": handle,
                    "method": "replace",
                    "author_name": self.user.full_name,
                    "author_email": self.user.email,
                },
            )
        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 2)


class CSVImportTest(ViewTestCase):
    test_file = TEST_CSV

    def test_import(self):
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        with open(self.test_file, "rb") as handle:
            self.client.post(
                reverse("upload_translation", kwargs=self.kw_translation),
                {
                    "file": handle,
                    "method": "translate",
                    "author_name": self.user.full_name,
                    "author_email": self.user.email,
                },
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

    source = "Hello, world!\n"
    target = "Nazdar svete!\n"
    test_match_1 = "Weblate Hello World 2016"
    test_match_2 = "Nazdar svete!"
    test_header = "attachment; filename=test-test-cs.po"
    test_source = "Orangutan has %d banana"
    test_source_plural = "Orangutan has %d bananas"

    def create_component(self):
        # Needs to create PO file to have language pack option
        return self.create_po()

    def setUp(self):
        super().setUp()
        # Add some content so that .mo files is non empty
        self.edit_unit(self.source, self.target)

    def assert_response_contains(self, response, *matches):
        """Replacement of assertContains to work on streamed responses."""
        self.assertEqual(
            response.status_code,
            200,
            "Couldn't retrieve content: Response code was %d" % response.status_code,
        )

        if response.streaming:
            content = b"".join(response.streaming_content)
        else:
            content = response.content
        for match in matches:
            self.assertIn(
                match.encode() if isinstance(match, str) else match,
                content,
                f"Couldn't find {match!r} in response",
            )

    def test_export(self):
        response = self.client.get(
            reverse("download_translation", kwargs=self.kw_translation)
        )
        self.assert_response_contains(response, self.test_match_1, self.test_match_2)
        self.assertEqual(response["Content-Disposition"], self.test_header)

    def export_format(self, fmt, **extra):
        extra["format"] = fmt
        return self.client.get(
            reverse("download_translation", kwargs=self.kw_translation), extra
        )

    def test_export_po(self):
        response = self.export_format("po")
        self.assert_response_contains(
            response,
            self.test_source,
            self.test_source_plural,
            "/projects/test/test/cs/",
        )

    def test_export_po_todo(self):
        response = self.export_format("po", q="state:<translated")
        self.assert_response_contains(
            response,
            self.test_source,
            self.test_source_plural,
            "/projects/test/test/cs/",
        )

    def test_export_tmx(self):
        response = self.export_format("tmx")
        self.assert_response_contains(response, self.test_source)

    def test_export_xliff(self):
        response = self.export_format("xliff")
        self.assert_response_contains(
            response, self.test_source, self.test_source_plural
        )

    def test_export_xliff11(self):
        response = self.export_format("xliff11")
        self.assert_response_contains(
            response, "urn:oasis:names:tc:xliff:document:1.1", self.test_source
        )

    def test_export_xlsx(self):
        response = self.export_format("xlsx")
        self.assertEqual(
            response["Content-Disposition"], "attachment; filename=test-test-cs.xlsx"
        )
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            "; charset=utf-8",
        )

    def test_export_xlsx_empty(self):
        response = self.export_format("xlsx", q="check:inconsistent")
        self.assertEqual(
            response["Content-Disposition"], "attachment; filename=test-test-cs.xlsx"
        )
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            "; charset=utf-8",
        )

    def test_export_invalid(self):
        response = self.export_format("invalid")
        self.assertEqual(response.status_code, 302)


class ExportMultifileTest(ExportTest):
    source = "Weblate - continuous localization"
    target = "Weblate - průběžná lokalizace"
    test_match_1 = b"PK\001\002"
    test_match_2 = b"PK\005\006"
    test_header = "attachment; filename=test-test-cs.zip"
    test_source = "https://www.youtube.com/watch?v=IVlXt6QdgdA"
    test_source_plural = "https://www.youtube.com/watch?v=IVlXt6QdgdA"

    def create_component(self):
        return self.create_appstore()


class FormTest(SimpleTestCase):
    def test_remove(self):
        form = SimpleUploadForm()
        form.remove_translation_choice("suggest")
        self.assertEqual(
            [x[0] for x in form.fields["method"].choices],
            ["translate", "approve", "fuzzy", "replace", "source", "add"],
        )


class ImportReplaceTest(ImportBaseTest):
    """Testing of file imports."""

    test_file = TEST_BADPLURALS

    def test_import(self):
        """Test importing normally."""
        response = self.do_import(method="replace")
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 2)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 2)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, TRANSLATION_PO)


class ImportSourceTest(ImportBaseTest):
    """Testing of source strings update imports."""

    test_file = TEST_POT_CHARSET
    expected = "Processed 3 strings from the uploaded files"
    expected_count = 3

    def setUp(self):
        super().setUp()
        self.kw_translation["lang"] = "en"
        self.translation_url = reverse("translation", kwargs=self.kw_translation)

    def test_import(self):
        """Test importing normally."""
        response = self.do_import(method="source", follow=True)
        self.assertRedirects(response, self.translation_url)
        messages = list(response.context["messages"])
        self.assertIn(self.expected, messages[0].message)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, self.expected_count)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, "")


class ImportAddTest(ImportBaseTest):
    """Testing of source strings update imports."""

    test_file = TEST_TBX

    def test_import(self):
        """Test importing normally."""
        response = self.do_import(method="add", follow=True)
        self.assertRedirects(response, self.translation_url)
        messages = [message.message for message in response.context["messages"]]
        self.assertIn(
            (
                "Error in parameter method: Select a valid choice. "
                "add is not one of the available choices."
            ),
            messages,
        )

        self.component.manage_units = True
        self.component.save(update_fields=["manage_units"])
        response = self.do_import(method="add", follow=True)
        self.assertRedirects(response, self.translation_url)
        messages = [message.message for message in response.context["messages"]]
        self.assertIn(
            (
                "Processed 164 strings from the uploaded files "
                "(skipped: 0, not found: 0, updated: 164)."
            ),
            messages,
        )

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 164)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 168)


class ImportSourceBrokenTest(ImportSourceTest):
    test_file = TEST_POT
    expected = 'Charset "CHARSET" is not a portable encoding name.'
    expected_count = 4


class DownloadMultiTest(ViewTestCase):
    def test_component(self):
        response = self.client.get(
            reverse("download_component", kwargs=self.kw_component)
        )
        self.assert_zip(response)

    def test_project(self):
        response = self.client.get(reverse("download_project", kwargs=self.kw_project))
        self.assert_zip(response)

    def test_project_lang(self):
        response = self.client.get(
            reverse(
                "download_lang_project",
                kwargs={"lang": "cs", "project": self.project.slug},
            )
        )
        self.assert_zip(response)

    def test_component_list(self):
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)
        response = self.client.get(
            reverse("download_component_list", kwargs={"name": "testcl"})
        )
        self.assert_zip(response)
