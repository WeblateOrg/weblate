# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for import and export."""

from io import BytesIO

from django.contrib.messages import ERROR
from django.test import SimpleTestCase
from django.urls import reverse
from openpyxl import load_workbook

from weblate.formats.helpers import NamedBytesIO
from weblate.trans.actions import ActionEvents
from weblate.trans.forms import SimpleUploadForm
from weblate.trans.models import ComponentList
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.state import STATE_READONLY

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
TEST_ANDROID_READONLY = get_test_file("strings-with-readonly.xml")
TEST_XLSX = get_test_file("cs.xlsx")
TEST_TBX = get_test_file("terms.tbx")

TRANSLATION_OURS = "Nazdar světe!\n"
TRANSLATION_PO = "Ahoj světe!\n"


class ImportBaseTest(ViewTestCase):
    """Base test of file imports."""

    test_file = TEST_PO

    def setUp(self) -> None:
        super().setUp()
        # We need extra privileges for overwriting
        self.user.is_superuser = True
        self.user.save()

    def do_import(self, test_file=None, follow=False, **kwargs):
        """Perform file import."""
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
                reverse("upload", kwargs=self.kw_translation),
                params,
                follow=follow,
            )


class ImportTest(ImportBaseTest):
    """Testing of file imports."""

    test_file = TEST_PO
    has_plurals = True

    def test_import_normal(self) -> None:
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

    def test_import_author(self) -> None:
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

    def test_import_overwrite(self) -> None:
        """Test importing with overwriting."""
        # Translate one unit
        self.change_unit(TRANSLATION_OURS)

        response = self.do_import(conflicts="replace-translated")
        self.assertRedirects(response, self.translation_url)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, TRANSLATION_PO)

    def test_import_no_overwrite(self) -> None:
        """Test importing without overwriting."""
        # Translate one unit
        self.change_unit(TRANSLATION_OURS)

        response = self.do_import()
        self.assertRedirects(response, self.translation_url)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, TRANSLATION_OURS)

    def test_import_fuzzy(self) -> None:
        """Test importing as fuzzy."""
        response = self.do_import(method="fuzzy")
        self.assertRedirects(response, self.translation_url)

        # Verify unit
        unit = self.get_unit()
        self.assertEqual(unit.target, TRANSLATION_PO)
        self.assertTrue(unit.fuzzy)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 1)
        self.assertEqual(translation.stats.all, 4)

    def test_import_suggest(self) -> None:
        """Test importing as suggestion."""
        response = self.do_import(method="suggest")
        self.assertRedirects(response, self.translation_url)

        # Verify unit
        unit = self.get_unit()
        self.assertFalse(unit.translated)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)
        self.assertEqual(translation.stats.suggestions, 1)

    def test_import_xliff(self) -> None:
        response = self.do_import(test_file=TEST_XLIFF, follow=True)
        self.assertContains(response, "updated: 1")
        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 1)


class ImportErrorTest(ImportBaseTest):
    """Testing import of broken files."""

    def test_mismatched_plurals(self) -> None:
        """
        Test importing a file with different number of plural forms.

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

    def test_import_normal(self) -> None:
        """Test importing normally."""
        response = self.do_import(fuzzy="")
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)

    def test_import_process(self) -> None:
        """Test importing including fuzzy strings."""
        response = self.do_import(fuzzy="process")
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 1)
        self.assertEqual(translation.stats.all, 4)

    def test_import_approve(self) -> None:
        """Test importing ignoring fuzzy flag."""
        response = self.do_import(fuzzy="approve")
        self.assertRedirects(response, self.translation_url)

        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 1)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 4)

    def test_import_review(self) -> None:
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
    has_plurals = False

    def create_component(self):
        return self.create_joomla()


class ImportCSVTest(ImportTest):
    has_plurals = False

    def create_component(self):
        return self.create_csv_mono()

    def test_import_source(self) -> None:
        with open(TEST_CSV, "rb") as handle:
            response = self.client.post(
                reverse(
                    "upload",
                    kwargs={"path": self.component.source_translation.get_url_path()},
                ),
                {
                    "file": handle,
                    "method": "replace",
                    "author_name": self.user.full_name,
                    "author_email": self.user.email,
                },
                follow=True,
            )
        self.assertRedirects(
            response, self.component.source_translation.get_absolute_url()
        )
        messages = list(response.context["messages"])
        self.assertIn("Processed 1 string from the uploaded files", messages[0].message)


class ImportJSONTest(ImportTest):
    has_plurals = False

    def create_component(self):
        return self.create_json()


class ImportJSONMonoTest(ImportTest):
    has_plurals = False

    def create_component(self):
        return self.create_json_mono()


class ImportPHPMonoTest(ImportTest):
    has_plurals = False

    def create_component(self):
        return self.create_php_mono()


class StringsImportTest(ImportTest):
    has_plurals = False

    def create_component(self):
        return self.create_iphone()


class AndroidImportTest(ViewTestCase):
    def create_component(self):
        return self.create_android()

    def test_import(self) -> None:
        with open(TEST_ANDROID, "rb") as handle:
            self.client.post(
                reverse("upload", kwargs=self.kw_translation),
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

    def test_replace(self) -> None:
        translation = self.get_translation()
        self.assertFalse(
            translation.change_set.filter(action=ActionEvents.REPLACE_UPLOAD).exists()
        )
        self.user.is_superuser = True
        self.user.save()
        with open(TEST_ANDROID, "rb") as handle:
            response = self.client.post(
                reverse(
                    "upload",
                    kwargs={"path": self.component.source_translation.get_url_path()},
                ),
                {
                    "file": handle,
                    "method": "replace",
                    "author_name": self.user.full_name,
                    "author_email": self.user.email,
                },
                follow=True,
            )
            messages = list(response.context["messages"])
            self.assertIn("updated: 2", messages[0].message)
        # Verify stats
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        self.assertEqual(translation.stats.all, 2)
        self.assertTrue(
            translation.change_set.filter(action=ActionEvents.REPLACE_UPLOAD).exists()
        )

    def test_readonly_upload_download(self) -> None:
        """Test upload and download with a file containing a non-translatable string."""
        project = self.component.project
        component = self.create_android(name="Component", project=project)
        self.user.is_superuser = True
        self.user.save()
        with open(TEST_ANDROID_READONLY, "rb") as handle:
            response = self.client.post(
                reverse(
                    "upload",
                    kwargs={"path": component.source_translation.get_url_path()},
                ),
                {
                    "file": handle,
                    "method": "replace",
                    "author_name": self.user.full_name,
                    "author_email": self.user.email,
                },
                follow=True,
            )
        messages = list(response.context["messages"])
        self.assertIn("updated: 3", messages[0].message)
        unit = component.source_translation.unit_set.get(context="string_two")
        self.assertEqual(unit.state, STATE_READONLY)

        response = self.client.get(
            reverse(
                "download",
                kwargs={"path": component.source_translation.get_url_path()},
            ),
            follow=True,
        )
        self.assertIn(
            'name="string_two" translatable="false"',
            response.getvalue().decode("utf-8"),
        )


class CSVImportTest(ViewTestCase):
    test_file = TEST_CSV

    def test_import(self) -> None:
        translation = self.get_translation()
        self.assertEqual(translation.stats.translated, 0)
        self.assertEqual(translation.stats.fuzzy, 0)
        with open(self.test_file, "rb") as handle:
            self.client.post(
                reverse("upload", kwargs=self.kw_translation),
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

    def setUp(self) -> None:
        super().setUp()
        # Add some content so that .mo files is non empty
        self.edit_unit(self.source, self.target)

    def assert_response_contains(self, response, *matches) -> None:
        """
        Assert that response contains matches.

        Replacement of assertContains to work on streamed responses.
        """
        self.assertEqual(
            response.status_code,
            200,
            f"Couldn't retrieve content: Response code was {response.status_code}",
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

    def test_export(self) -> None:
        response = self.client.get(reverse("download", kwargs=self.kw_translation))
        self.assert_response_contains(response, self.test_match_1, self.test_match_2)
        self.assertEqual(response["Content-Disposition"], self.test_header)

    def export_format(self, fmt, **extra):
        extra["format"] = fmt
        return self.client.get(reverse("download", kwargs=self.kw_translation), extra)

    def test_export_po(self) -> None:
        response = self.export_format("po")
        self.assert_response_contains(
            response,
            self.test_source,
            self.test_source_plural,
            "/projects/test/test/cs/",
        )

    def test_export_po_todo(self) -> None:
        response = self.export_format("po", q="state:<translated")
        self.assert_response_contains(
            response,
            self.test_source,
            self.test_source_plural,
            "/projects/test/test/cs/",
        )

    def test_export_tmx(self) -> None:
        response = self.export_format("tmx")
        self.assert_response_contains(response, self.test_source)

    def test_export_xliff(self) -> None:
        response = self.export_format("xliff")
        self.assert_response_contains(
            response, self.test_source, self.test_source_plural
        )

    def test_export_xliff11(self) -> None:
        response = self.export_format("xliff11")
        self.assert_response_contains(
            response, "urn:oasis:names:tc:xliff:document:1.1", self.test_source
        )

    def test_export_xlsx(self) -> None:
        response = self.export_format("xlsx")
        self.assert_excel(response)
        self.assertEqual(
            response["Content-Disposition"], "attachment; filename=test-test-cs.xlsx"
        )

    def test_export_xlsx_empty(self) -> None:
        response = self.export_format("xlsx", q="check:inconsistent")
        self.assert_excel(response)
        self.assertEqual(
            response["Content-Disposition"], "attachment; filename=test-test-cs.xlsx"
        )

    def test_export_invalid(self) -> None:
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
    def test_remove(self) -> None:
        form = SimpleUploadForm()
        form.remove_translation_choice("suggest")
        self.assertEqual(
            [x[0] for x in form.fields["method"].choices],
            ["translate", "approve", "fuzzy", "replace", "source", "add"],
        )


class ImportReplaceTest(ImportBaseTest):
    """Testing of file imports."""

    test_file = TEST_BADPLURALS

    def test_import(self) -> None:
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
    expected_uploads = 1

    def setUp(self) -> None:
        super().setUp()
        self.translation = self.component.source_translation

    def test_import(self) -> None:
        """Test importing normally."""
        translation = self.get_translation()
        self.assertFalse(
            translation.change_set.filter(action=ActionEvents.SOURCE_UPLOAD).exists()
        )
        response = self.do_import(method="source", follow=True)
        self.assertRedirects(response, self.translation.get_absolute_url())
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

        self.assertEqual(
            translation.change_set.filter(action=ActionEvents.SOURCE_UPLOAD).count(),
            self.expected_uploads,
        )


class ImportAddTest(ImportBaseTest):
    """Testing of source strings update imports."""

    test_file = TEST_TBX

    def test_import(self) -> None:
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
    expected_uploads = 0


class DownloadMultiTest(ViewTestCase):
    def test_component(self) -> None:
        response = self.client.get(reverse("download", kwargs=self.kw_component))
        self.assert_zip(response, "test/test/po/cs.po")

    def test_project(self) -> None:
        response = self.client.get(
            reverse("download", kwargs={"path": self.project.get_url_path()})
        )
        self.assert_zip(response, "test/test/po/de.po")

    def test_project_lang(self) -> None:
        response = self.client.get(
            reverse("download", kwargs={"path": (self.project.slug, "-", "cs")})
        )
        self.assert_zip(response, "test/test/po/cs.po")

    def test_component_list(self) -> None:
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)
        response = self.client.get(
            reverse("download_component_list", kwargs={"name": "testcl"})
        )
        self.assert_zip(response, "test/test/po/cs.po")

    def test_component_csv(self) -> None:
        response = self.client.get(
            reverse("download", kwargs=self.kw_component), {"format": "zip:csv"}
        )
        self.assert_zip(response, "test-test-cs.csv")

    def test_component_xlsx(self) -> None:
        response = self.client.get(
            reverse("download", kwargs=self.kw_component), {"format": "zip:xlsx"}
        )
        content = self.assert_zip(response, "test-test-cs.xlsx")
        load_workbook(BytesIO(content))


EXPECTED_CSV = """location,source,target,id,fuzzy,context,translator_comments,developer_comments\r
,"Hello, world!
",,,False,hello,,\r
,"Orangutan has %d banana.
",,,False,orangutan,,\r
,"Try Weblate at https://demo.weblate.org/!
",,,False,try,,\r
,Thank you for using Weblate.,,,False,thanks,,\r
"""

UPLOAD_CSV = """
"location","source","target","id","fuzzy","context","translator_comments","developer_comments"
"","Hello, world!
","Nazdar, světe!
","","False","hello","",""
"""


class ImportExportAddTest(ViewTestCase):
    def create_component(self):
        return self.create_json_mono()

    def test_notchanged(self) -> None:
        response = self.client.get(
            reverse("download", kwargs=self.kw_translation),
            {"format": "csv"},
        )
        self.assertEqual(response.content.decode(), EXPECTED_CSV)

        handle = NamedBytesIO("test.csv", UPLOAD_CSV.encode())
        params = {
            "file": handle,
            "method": "translate",
            "author_name": self.user.full_name,
            "author_email": self.user.email,
        }
        response = self.client.post(
            reverse("upload", kwargs=self.kw_translation),
            params,
            follow=True,
        )
        self.assertContains(response, "(skipped: 0, not found: 0, updated: 1)")

    def test_changed(self) -> None:
        self.edit_unit("Hello, world!\n", "Hi, World!\n", "en")
        response = self.client.get(
            reverse("download", kwargs=self.kw_translation),
            {"format": "csv"},
        )
        self.assertEqual(
            response.content.decode(), EXPECTED_CSV.replace("Hello, world", "Hi, World")
        )

        handle = NamedBytesIO(
            "test.csv", UPLOAD_CSV.replace("Hello, world", "Hi, World").encode()
        )
        params = {
            "file": handle,
            "method": "translate",
            "author_name": self.user.full_name,
            "author_email": self.user.email,
        }
        response = self.client.post(
            reverse("upload", kwargs=self.kw_translation),
            params,
            follow=True,
        )
        self.assertContains(response, "(skipped: 0, not found: 0, updated: 1)")
