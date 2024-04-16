# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.formats.base import EmptyFormat
from weblate.formats.exporters import (
    AndroidResourceExporter,
    BaseExporter,
    CSVExporter,
    JSONExporter,
    JSONNestedExporter,
    MoExporter,
    PoExporter,
    PoXliffExporter,
    StringsExporter,
    TBXExporter,
    XliffExporter,
    XlsxExporter,
)
from weblate.formats.helpers import NamedBytesIO
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
