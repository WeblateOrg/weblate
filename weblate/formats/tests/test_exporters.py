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

from weblate.formats.base import EmptyFormat
from weblate.formats.exporters import (
    AndroidResourceExporter,
    CSVExporter,
    JSONExporter,
    MoExporter,
    PoExporter,
    PoXliffExporter,
    StringsExporter,
    TBXExporter,
    XliffExporter,
    XlsxExporter,
)
from weblate.formats.helpers import BytesIOMode
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


class PoExporterTest(BaseTestCase):
    _class = PoExporter
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
            **kwargs
        )

    def check_export(self, exporter):
        output = exporter.serialize()
        self.assertIsNotNone(output)
        return output

    def check_plurals(self, result):
        self.assertIn(b"msgid_plural", result)
        self.assertIn(b"msgstr[2]", result)

    def check_unit(self, nplurals=3, template=None, source_info=None, **kwargs):
        if nplurals == 3:
            formula = "n==0 ? 0 : n==1 ? 1 : 2"
        else:
            formula = "0"
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
        translation.store = EmptyFormat(BytesIOMode("", b""))
        unit = Unit(translation=translation, id_hash=-1, **kwargs)
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

    def test_unit(self):
        self.check_unit(source="xxx", target="yyy")

    def test_unit_mono(self):
        self.check_unit(source="xxx", target="yyy", template="template")

    def test_unit_markup(self):
        self.check_unit(source="<b>foo</b>", target="<b>bar</b>")

    def test_unit_special(self):
        self.check_unit(source="bar\x1e\x1efoo", target="br\x1eff")

    def _encode(self, string):
        return string.encode("utf-8")

    def test_unit_plural(self):
        result = self.check_unit(
            source="xxx\x1e\x1efff",
            target="yyy\x1e\x1efff\x1e\x1ewww",
            state=STATE_TRANSLATED,
        )
        self.check_plurals(result)

    def test_unit_plural_one(self):
        self.check_unit(
            nplurals=1, source="xxx\x1e\x1efff", target="yyy", state=STATE_TRANSLATED
        )

    def test_unit_not_translated(self):
        self.check_unit(
            nplurals=1, source="xxx\x1e\x1efff", target="yyy", state=STATE_EMPTY
        )

    def test_context(self):
        result = self.check_unit(
            source="foo", target="bar", context="context", state=STATE_TRANSLATED
        )
        if self._has_context:
            self.assertIn(self._encode("context"), result)
        elif self._has_context is not None:
            self.assertNotIn(self._encode("context"), result)

    def test_extra_info(self):
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

    def setUp(self):
        self.exporter = self.get_exporter()

    def test_has_get_storage(self):
        self.assertTrue(hasattr(self.exporter, "get_storage"))

    def test_has_setsourcelanguage(self):
        self.assertTrue(hasattr(self.exporter.storage, "setsourcelanguage"))

    def test_has_settargetlanguage(self):
        self.assertTrue(hasattr(self.exporter.storage, "settargetlanguage"))

    def test_has_unitclass(self):
        self.assertTrue(hasattr(self.exporter.storage, "UnitClass"))

    def test_has_addunit(self):
        self.assertTrue(hasattr(self.exporter.storage, "addunit"))


class PoXliffExporterTest(PoExporterTest):
    _class = PoXliffExporter
    _has_context = True

    def check_plurals(self, result):
        self.assertIn(b"[2]", result)

    def test_xml_nodes(self):
        xml = """<xliff:g
            xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2"
            example="Launcher3"
            id="app_name">
            %1$s
        </xliff:g>"""
        result = self.check_unit(source="x " + xml, target="y " + xml).decode()
        self.assertIn("<g", result)

    def test_php_code(self):
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

    def check_plurals(self, result):
        # Doesn't support plurals
        return


class TBXExporterTest(PoExporterTest):
    _class = TBXExporter
    _has_context = False

    def check_plurals(self, result):
        # Doesn't support plurals
        return


class MoExporterTest(PoExporterTest):
    _class = MoExporter
    _has_context = True
    _has_comments = False

    def check_plurals(self, result):
        self.assertIn(b"www", result)


class CSVExporterTest(PoExporterTest):
    _class = CSVExporter
    _has_context = True

    def check_plurals(self, result):
        # Doesn't support plurals
        pass

    def test_escaping(self):
        output = self.check_unit(
            source='=HYPERLINK("https://weblate.org/"&A1, "Weblate")', target="yyy"
        )
        self.assertIn(b"\"'=HYPERLINK", output)


class XlsxExporterTest(PoExporterTest):
    _class = XlsxExporter
    _has_context = False
    _has_comments = False

    def check_plurals(self, result):
        # Doesn't support plurals
        pass


class AndroidResourceExporterTest(PoExporterTest):
    _class = AndroidResourceExporter
    _has_comments = False

    def check_plurals(self, result):
        self.assertIn(b"<plural", result)


class JSONExporterTest(PoExporterTest):
    _class = JSONExporter
    _has_comments = False

    def check_plurals(self, result):
        # Doesn't support plurals
        pass


class StringsExporterTest(PoExporterTest):
    _class = StringsExporter
    _has_comments = False

    def _encode(self, string):
        # Skip BOM
        return string.encode("utf-16")[2:]

    def check_plurals(self, result):
        # Doesn't support plurals
        pass
