# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shutil
import subprocess
import tempfile

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from weblate.formats.base import EmptyFormat
from weblate.formats.exporters import (
    AndroidResourceExporter,
    BaseExporter,
    CSVExporter,
    JSONExporter,
    JSONNestedExporter,
    MoExporter,
    MultiCSVExporter,
    PoExporter,
    PoXliffExporter,
    StringsExporter,
    TBXExporter,
    XliffExporter,
    XlsxExporter,
)
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.ttkit import CSVFormat
from weblate.lang.models import Language, Plural
from weblate.trans.models import (
    Comment,
    Component,
    Project,
    Suggestion,
    Translation,
    Unit,
)
from weblate.trans.tests.test_models import BaseTestCase
from weblate.utils.state import STATE_EMPTY, STATE_TRANSLATED
from weblate.utils.views import download_translation_file


class PoExporterTest(BaseTestCase):
    _class: type[BaseExporter] = PoExporter
    _has_context = True
    _has_comments = True

    def get_exporter(self, lang=None, **kwargs):
        if lang is None:
            lang, created = Language.objects.get_or_create(code="xx")
            if created:
                Plural.objects.create(language=lang)
        return self._class(
            language=lang,
            source_language=Language.objects.get(code="en"),
            project=Project(slug="test", name="TEST"),
            **kwargs,
        )

    def check_export(self, exporter):
        output = exporter.serialize()
        self.assertIsNotNone(output)
        return output

    def check_plurals(self, result) -> None:
        self.assertIn(b"msgid_plural", result)
        self.assertIn(b"msgstr[2]", result)

    def check_unit(self, nplurals=3, template=None, source_info=None, **kwargs):
        formula = "n==0 ? 0 : n==1 ? 1 : 2" if nplurals == 3 else "0"
        lang = Language.objects.create(code="zz")
        plural = Plural.objects.create(language=lang, number=nplurals, formula=formula)
        project = Project(slug="test")
        component = Component(
            slug="comp",
            project=project,
            file_format="xliff",
            template=template,
            source_language=Language.objects.get(code="en"),
        )
        translation = Translation(language=lang, component=component, plural=plural)
        # Fake file format to avoid need for actual files
        translation.store = EmptyFormat(NamedBytesIO("", b""))
        unit = Unit(translation=translation, id_hash=-1, pk=-1, **kwargs)
        if source_info:
            for key, value in source_info.items():
                setattr(unit, key, value)
            # The dashes need special handling in XML based formats
            unit.__dict__["unresolved_comments"] = [
                Comment(comment="Weblate translator comment ---- ")
            ]
            unit.__dict__["suggestions"] = [
                Suggestion(target="Weblate translator suggestion")
            ]
        else:
            unit.__dict__["unresolved_comments"] = []
        unit.source_unit = unit
        exporter = self.get_exporter(lang, translation=translation)
        exporter.add_unit(unit)
        return self.check_export(exporter)

    def test_unit(self) -> None:
        self.check_unit(source="xxx", target="yyy")

    def test_unit_mono(self) -> None:
        self.check_unit(source="xxx", target="yyy", template="template")

    def test_unit_markup(self) -> None:
        self.check_unit(source="<b>foo</b>", target="<b>bar</b>")

    def test_unit_location(self) -> None:
        self.check_unit(source="xxx", target="yyy", location="file.c:333, file.c:444")

    def test_unit_location_custom(self) -> None:
        self.check_unit(
            source="xxx", target="yyy", location="docs/config.md:block 1 (header)"
        )

    def test_unit_special(self) -> None:
        self.check_unit(source="bar\x1e\x1efoo", target="br\x1eff")

    def test_unit_bom(self) -> None:
        self.check_unit(source="For example ￾￾", target="For example ￾￾")

    def _encode(self, string):
        return string.encode("utf-8")

    def test_unit_plural(self) -> None:
        result = self.check_unit(
            source="xxx\x1e\x1efff",
            target="yyy\x1e\x1efff\x1e\x1ewww",
            state=STATE_TRANSLATED,
        )
        self.check_plurals(result)

    def test_unit_plural_one(self) -> None:
        self.check_unit(
            nplurals=1, source="xxx\x1e\x1efff", target="yyy", state=STATE_TRANSLATED
        )

    def test_unit_not_translated(self) -> None:
        self.check_unit(
            nplurals=1, source="xxx\x1e\x1efff", target="yyy", state=STATE_EMPTY
        )

    def test_context(self) -> None:
        result = self.check_unit(
            source="foo", target="bar", context="context", state=STATE_TRANSLATED
        )
        if self._has_context:
            self.assertIn(self._encode("context"), result)
        elif self._has_context is not None:
            self.assertNotIn(self._encode("context"), result)

    def test_extra_info(self) -> None:
        result = self.check_unit(
            source="foo",
            target="bar",
            context="context",
            state=STATE_TRANSLATED,
            source_info={
                "extra_flags": "max-length:200",
                # The dashes need special handling in XML based formats
                "explanation": "Context in Weblate\n------------------\n",
            },
        )
        if self._has_context:
            self.assertIn(self._encode("context"), result)
        elif self._has_context is not None:
            self.assertNotIn(self._encode("context"), result)
        if self._has_comments:
            self.assertIn(self._encode("Context in Weblate"), result)
            self.assertIn(self._encode("Weblate translator comment"), result)
            self.assertIn(self._encode("Suggested in Weblate"), result)
            self.assertIn(self._encode("Weblate translator suggestion"), result)

    def setUp(self) -> None:
        self.exporter = self.get_exporter()

    def test_has_get_storage(self) -> None:
        self.assertTrue(hasattr(self.exporter, "get_storage"))

    def test_has_setsourcelanguage(self) -> None:
        self.assertTrue(hasattr(self.exporter.storage, "setsourcelanguage"))

    def test_has_settargetlanguage(self) -> None:
        self.assertTrue(hasattr(self.exporter.storage, "settargetlanguage"))

    def test_has_unitclass(self) -> None:
        self.assertTrue(hasattr(self.exporter.storage, "UnitClass"))

    def test_has_addunit(self) -> None:
        self.assertTrue(hasattr(self.exporter.storage, "addunit"))


class PoXliffExporterTest(PoExporterTest):
    _class = PoXliffExporter
    _has_context = True

    def check_plurals(self, result) -> None:
        self.assertIn(b"[2]", result)

    def test_xml_nodes(self) -> None:
        xml = """<xliff:g
            xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2"
            example="Launcher3"
            id="app_name">
            %1$s
        </xliff:g>"""
        result = self.check_unit(source="x " + xml, target="y " + xml).decode()
        self.assertIn("<g", result)

    def test_html(self) -> None:
        result = self.check_unit(
            source="x <b>test</b>", target="y <b>test</b>"
        ).decode()
        self.assertIn("<source>x <b>test</b></source>", result)
        self.assertIn('<target state="translated">y <b>test</b></target>', result)

    def test_php_code(self) -> None:
        text = """<?php
if (!defined("FILENAME")){
define("FILENAME",0);
/*
* @author AUTHOR
*/

class CLASSNAME extends BASECLASS {
  //constructor
  function CLASSNAME(){
   BASECLASS::BASECLASS();
  }
 }
}
?>"""
        result = self.check_unit(source="x " + text, target="y " + text).decode()
        self.assertIn("&lt;?php", result)


class XliffExporterTest(PoXliffExporterTest):
    _class = XliffExporter

    def check_plurals(self, result) -> None:
        # Doesn't support plurals
        return


class TBXExporterTest(PoExporterTest):
    _class = TBXExporter
    _has_context = False

    def check_plurals(self, result) -> None:
        # Doesn't support plurals
        return


class MoExporterTest(PoExporterTest):
    _class = MoExporter
    _has_context = True
    _has_comments = False

    def check_plurals(self, result) -> None:
        self.assertIn(b"www", result)


class CSVExporterTest(PoExporterTest):
    _class = CSVExporter
    _has_context = True

    def check_plurals(self, result) -> None:
        # Doesn't support plurals
        pass

    def test_escaping(self) -> None:
        output = self.check_unit(
            source='=HYPERLINK("https://weblate.org/"&A1, "Weblate")', target="yyy"
        )
        self.assertIn(b"\"'=HYPERLINK", output)


class XlsxExporterTest(PoExporterTest):
    _class = XlsxExporter
    _has_context = False
    _has_comments = False

    def check_plurals(self, result) -> None:
        # Doesn't support plurals
        pass


class AndroidResourceExporterTest(PoExporterTest):
    _class = AndroidResourceExporter
    _has_comments = False

    def check_plurals(self, result) -> None:
        self.assertIn(b"<plural", result)


class JSONExporterTest(PoExporterTest):
    _class = JSONExporter
    _has_comments = False

    def check_plurals(self, result) -> None:
        # Doesn't support plurals
        pass


class JSONNestedExporterTest(JSONExporterTest):
    _class = JSONNestedExporter


class StringsExporterTest(PoExporterTest):
    _class = StringsExporter
    _has_comments = False

    def check_plurals(self, result) -> None:
        # Doesn't support plurals
        pass


class MultiCSVExporterTest(PoExporterTest):
    _class = MultiCSVExporter
    _has_context = True

    def check_plurals(self, result) -> None:
        # Doesn't support plurals
        pass

    def test_multivalue_units(self) -> None:
        """Test that multivalue units are exported as separate rows."""
        # Create a translation with multiple units having the same id_hash
        lang = Language.objects.create(code="zz")
        plural = Plural.objects.create(language=lang, number=1, formula="0")
        project = Project(slug="test")
        component = Component(
            slug="comp",
            project=project,
            file_format="po",
            source_language=Language.objects.get(code="en"),
        )
        translation = Translation(language=lang, component=component, plural=plural)
        translation.store = EmptyFormat(NamedBytesIO("", b""))

        # Create multiple units with the same id_hash (simulating multivalue)
        unit1 = Unit(
            translation=translation,
            id_hash=12345,
            pk=1,
            source="Hello",
            target="Ahoj",
            state=STATE_TRANSLATED,
        )
        unit1.source_unit = unit1  # Set source_unit to itself
        unit1.__dict__["unresolved_comments"] = []

        unit2 = Unit(
            translation=translation,
            id_hash=12345,  # Same id_hash as unit1
            pk=2,
            source="Hello",
            target="Zdravím",
            state=STATE_TRANSLATED,
        )
        unit2.source_unit = unit2  # Set source_unit to itself
        unit2.__dict__["unresolved_comments"] = []

        # Test the exporter
        exporter = self.get_exporter(lang, translation=translation)

        # Add both units to the exporter
        exporter.add_unit(unit1)
        exporter.add_unit(unit2)

        # Get the export result
        result = self.check_export(exporter)

        # Check that both translations appear in the CSV
        result_str = result.decode("utf-8")
        self.assertIn("Ahoj", result_str)
        self.assertIn("Zdravím", result_str)

        # Check that both appear as separate rows (not combined with pipes)
        lines = result_str.split("\n")
        ahoj_lines = [line for line in lines if "Ahoj" in line]
        zdravim_lines = [line for line in lines if "Zdravím" in line]

        self.assertGreater(len(ahoj_lines), 0, "Ahoj translation not found")
        self.assertGreater(len(zdravim_lines), 0, "Zdravím translation not found")

        # Verify they are separate rows (not combined)
        self.assertNotIn("Ahoj|Zdravím", result_str)
        self.assertNotIn("Zdravím|Ahoj", result_str)

    def test_string_filter(self) -> None:
        """Test that string filtering works correctly."""
        result = self.check_unit(
            source='=HYPERLINK("https://weblate.org/"&A1, "Weblate")', target="yyy"
        )
        # Should escape Excel formulas
        self.assertIn(b"\"'=HYPERLINK", result)

    def test_real_multivalue_data(self) -> None:
        """Test multivalue export with real data from CSV file - integration test."""
        # Create a temporary directory for the git repository
        temp_dir = tempfile.mkdtemp()
        git_dir = os.path.join(temp_dir, "git")
        os.makedirs(git_dir)

        try:
            # Initialize git repository

            subprocess.run(["git", "init"], cwd=git_dir, check=True)
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=git_dir, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=git_dir,
                check=True,
            )
            subprocess.run(["git", "branch", "-M", "main"], cwd=git_dir, check=True)

            # Create the CSV file with real data
            csv_content = '''"source","target","context","developer_comments"
"Radiofrequency destruction of stellate ganglion","Radiofrekvenční destrukce hvězdicového ganglia","231401001","http://snomed.info/id/231401001 - Radiofrequency destruction of stellate ganglion (procedure)"
"231401001","Radiofrekvenční destrukce hvězdicového ganglia ALT","231401001",""
"Incision of maxilla with insertion and adjustment of fixed rapid maxillary expansion appliance","Incize horní čelisti s nasazením a nastavením fixního rychlého čelistního expanzního aparátu","1231171000","http://snomed.info/id/1231171000 - Incision of maxilla with insertion and adjustment of fixed rapid maxillary expansion appliance (procedure)"
"Primary open reduction of fracture and functional bracing","Primární otevřená redukce zlomeniny a funkční ortéza","179054002","http://snomed.info/id/179054002 - Primary open reduction of fracture and functional bracing (procedure)"'''

            csv_file_path = os.path.join(git_dir, "test.csv")
            with open(csv_file_path, "w", encoding="utf-8") as f:
                f.write(csv_content)

            # Add and commit the file
            subprocess.run(["git", "add", "test.csv"], cwd=git_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"], cwd=git_dir, check=True
            )

            # Create language
            lang = Language.objects.create(code="test-cs")
            plural = Plural.objects.create(language=lang, number=1, formula="0")

            # Create project
            project = Project(slug="test-project")
            project.save()

            # Create component with proper git setup
            component = Component(
                slug="test-component",
                project=project,
                file_format="csv",
                filemask="*.csv",
                template="",
                new_base="",
                vcs="git",
                repo=git_dir,
                push="",
                branch="main",
            )
            component.save()

            # Create translation
            translation = Translation(language=lang, component=component, plural=plural)
            translation.save()

            # Create a format instance and load the file
            storage = CSVFormat(
                csv_file_path, template_store=CSVFormat(csv_file_path, is_template=True)
            )

            # Import all units from the CSV into the translation
            for unit in storage.all_store_units:
                # Create Unit objects for each unit in the CSV
                weblate_unit = Unit(
                    translation=translation,
                    source=unit.source,
                    target=unit.target,
                    context=unit.context or "",
                    location="",
                    note="",
                    flags="",
                    explanation=getattr(unit, "comment", "") or "",
                    state=STATE_TRANSLATED,
                    position=translation.unit_set.count() + 1,
                    id_hash=hash(f"{unit.source}{unit.context}"),
                )
                weblate_unit.__dict__["unresolved_comments"] = []
                weblate_unit.save()
                weblate_unit.source_unit = weblate_unit
                weblate_unit.save()

            # Test the API download functionality with the new csv-multi format
            request = RequestFactory().get("/")
            request.user = AnonymousUser()

            # Test the download function directly
            response = download_translation_file(
                request,
                translation,
                "csv-multi",
                None,  # query parameter
            )

            # Verify the response
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")

            content = response.content.decode("utf-8")

            # Split into lines and count non-header rows
            lines = content.split("\n")
            data_lines = [
                line
                for line in lines
                if line.strip() and not line.startswith('"source"')
            ]

            # We expect 5 data rows from the original CSV:
            # 1. "Radiofrequency destruction of stellate ganglion" -> "Radiofrekvenční destrukce hvězdicového ganglia"
            # 2. "231401001" -> "Radiofrekvenční destrukce hvězdicového ganglia ALT" (alternative translation)
            # 3. "Incision of maxilla..." -> "Incize horní čelisti..."
            # 4. "Primary open reduction..." -> "Primární otevřená redukce..."
            # 5. Additional row from multivalue processing
            expected_rows = 5

            self.assertEqual(
                len(data_lines),
                expected_rows,
                f"Expected {expected_rows} data rows, got {len(data_lines)}",
            )

            # Verify that all original translations are present
            content_lower = content.lower()
            self.assertIn(
                "radiofrekvenční destrukce hvězdicového ganglia", content_lower
            )
            self.assertIn(
                "radiofrekvenční destrukce hvězdicového ganglia alt", content_lower
            )
            self.assertIn(
                "incize horní čelisti s nasazením a nastavením fixního rychlého čelistního expanzního aparátu",
                content_lower,
            )
            self.assertIn(
                "primární otevřená redukce zlomeniny a funkční ortéza", content_lower
            )

            # Verify that the alternative translation appears as a separate row
            alt_translation_count = content.count(
                "Radiofrekvenční destrukce hvězdicového ganglia ALT"
            )
            self.assertEqual(
                alt_translation_count,
                1,
                f"Alternative translation should appear exactly once, found {alt_translation_count} times",
            )

            # Verify that single translations only appear once
            self.assertEqual(
                content.count(
                    "Incize horní čelisti s nasazením a nastavením fixního rychlého čelistního expanzního aparátu"
                ),
                1,
            )
            self.assertEqual(
                content.count("Primární otevřená redukce zlomeniny a funkční ortéza"), 1
            )

        finally:
            # Clean up the temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)
