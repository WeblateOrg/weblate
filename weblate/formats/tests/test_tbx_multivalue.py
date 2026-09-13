# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""TBX concepts use independent source and target alternatives."""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from lxml import etree
from lxml import html as lxml_html

from weblate.api.serializers import UnitSerializer
from weblate.auth.models import get_anonymous
from weblate.checks.flags import Flags
from weblate.checks.glossary import GlossaryCheck
from weblate.formats.exporters import TBXExporter
from weblate.formats.ttkit import TBXFormat, TBXUnit
from weblate.glossary.models import (
    get_glossary_terms,
    get_glossary_tuples,
    iter_glossary_alternatives,
    prepare_glossary_alternatives,
)
from weblate.lang.models import Language
from weblate.machinery.llm import BaseLLMTranslation
from weblate.machinery.microsoft import MicrosoftCognitiveTranslation
from weblate.trans.forms import PluralField
from weblate.trans.models import Unit
from weblate.trans.tests.factories import make_unit
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.util import join_plural
from weblate.utils.hash import calculate_hash
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED
from weblate.utils.terminology import reconcile_terms

TBX = b"""<martif type="TBX"><text><body><termEntry id="concept-example">
<descrip type="definition">A program.</descrip>
<langSet xml:lang="en">
<tig id="source-legacy"><term>application</term><termNote type="administrativeStatus">obsolete</termNote></tig>
<tig id="source-short"><term>app</term></tig>
</langSet>
<langSet xml:lang="fr">
<tig id="target-full"><term>application</term><note from="translator">Full name</note></tig>
<tig><term>appli</term></tig>
<tig id="target-blocked"><term>logiciel</term><termNote type="administrativeStatus">forbidden</termNote></tig>
</langSet>
<langSet xml:lang="de"><tig><term>Software</term></tig></langSet>
</termEntry></body></text></martif>"""


class TBXMultivalueTest(SimpleTestCase):
    @staticmethod
    def parse(data: bytes = TBX, language: str = "fr") -> TBXFormat:
        return TBXFormat(BytesIO(data), language_code=language, source_language="en")

    def test_independent_alternatives_and_identity(self) -> None:
        storage = self.parse()
        self.assertEqual(len(storage.content_units), 1)
        unit = storage.content_units[0]
        self.assertEqual(unit.source, join_plural(["application", "app"]))
        self.assertEqual(unit.target, join_plural(["application", "appli", "logiciel"]))
        self.assertEqual(unit.id_hash, calculate_hash("application", "concept-example"))
        self.assertEqual(unit.flags, Flags())
        self.assertEqual(
            unit.tbx_terms["source"][0]["administrative_status"], "obsolete"
        )
        self.assertIsNone(unit.tbx_terms["target"][1]["id"])

    def test_edit_and_reserialize(self) -> None:
        storage = self.parse()
        unit = storage.content_units[0]
        german = etree.tostring(unit.unit.get_target_dom("de"))
        unit.set_target(["appli", "new name", "logiciel", "extra"])
        unit.set_source_explanation("New concept definition")
        terms = unit.unit.get_target_terms()
        self.assertEqual(
            [term.id for term in terms], [None, "target-full", "target-blocked", None]
        )
        self.assertIn("Full name", [note.text for note in terms[1].notes])
        self.assertEqual(etree.tostring(unit.unit.get_target_dom("de")), german)
        restored = self.parse(bytes(storage.store)).content_units[0]
        self.assertEqual(restored.target, unit.target)
        self.assertEqual(restored.tbx_terms, unit.tbx_terms)

    def test_dnt_missing_target(self) -> None:
        data = TBX.replace(
            b'<descrip type="definition">',
            b'<descrip type="Translation needed">No</descrip><descrip type="definition">',
        )
        unit = self.parse(data, language="ko").content_units[0]
        self.assertEqual(unit.target, "")
        self.assertFalse(unit.is_translated())
        self.assertTrue(unit.is_readonly())
        self.assertIn("read-only", unit.flags)
        self.assertEqual(len(unit.tbx_terms["source"]), 2)

    def test_machinery_expands_permitted_alternatives(self) -> None:
        parsed = self.parse().content_units[0]
        term = make_unit(source=parsed.source, target=parsed.target)
        term.details["tbx_terms"] = parsed.tbx_terms
        term.source_unit.details["tbx_terms"] = {"source": parsed.tbx_terms["source"]}
        term.matched_sources = ("app",)
        term.glossary_positions = ((0, 3),)
        edited = make_unit(source="app")
        with patch("weblate.machinery.llm.get_glossary_terms", return_value=[term]):
            entries = BaseLLMTranslation._get_glossary_entries([edited])  # ruff: ignore[private-member-access]
        self.assertEqual(
            entries,
            [
                {"source": "app", "target": target}
                for target in ("application", "appli")
            ],
        )
        # A forbidden first alternative must not hide a later permitted term.
        term.target = join_plural(["logiciel", "appli", "application"])
        machine = MicrosoftCognitiveTranslation(
            {"region": "", "endpoint_url": "example.com"}
        )
        with patch(
            "weblate.machinery.microsoft.get_glossary_terms", return_value=[term]
        ):
            highlights = list(machine.get_highlights("app", edited))
        self.assertEqual(len(highlights), 1)
        self.assertEqual(
            machine.format_replacement(*highlights[0]),
            '<mstrans:dictionary translation="appli">app</mstrans:dictionary>',
        )

    def test_new_concept(self) -> None:
        storage = self.parse()
        unit = storage.create_unit("new", ["one", "two"], ["un", "deux", "trois"])
        wrapped: TBXUnit = TBXUnit(storage, unit)
        self.assertEqual(wrapped.source, join_plural(["one", "two"]))
        self.assertEqual(wrapped.target, join_plural(["un", "deux", "trois"]))

    def test_scalar_consumers_and_metadata_reconciliation(self) -> None:
        parsed = self.parse().content_units[0]
        unit = Unit(
            source=parsed.source,
            target=parsed.target,
            state=STATE_TRANSLATED,
            details={"tbx_terms": parsed.tbx_terms},
        )
        unit.all_flags = Flags()
        unit.matched_sources = ("app",)
        alternatives = list(iter_glossary_alternatives([unit]))
        self.assertEqual([item.source for item in alternatives], ["app"] * 3)
        self.assertNotIn("forbidden", alternatives[0].all_flags)
        self.assertIn("forbidden", alternatives[2].all_flags)
        self.assertEqual(list(get_glossary_tuples([unit])), [("app", "application")])
        reconciled = reconcile_terms(parsed.tbx_terms["target"], ["appli", "renamed"])
        self.assertEqual([record["id"] for record in reconciled], [None, "target-full"])

    def test_explanation_edit_preserves_term_note(self) -> None:
        storage = self.parse()
        unit = storage.content_units[0]
        unit.set_target(["application"])
        self.assertEqual(unit.explanation, "")
        unit.set_explanation("Language explanation")
        self.assertEqual(unit.explanation, "Language explanation")
        unit.set_explanation("")
        self.assertEqual(unit.explanation, "")
        self.assertEqual(unit.tbx_terms["target"][0]["notes"][-1]["text"], "Full name")

    def test_glossary_check_accepts_permitted_alternatives(self) -> None:
        parsed = self.parse().content_units[0]
        term = Unit(
            source=parsed.source,
            target=parsed.target,
            state=STATE_TRANSLATED,
            details={"tbx_terms": parsed.tbx_terms},
        )
        term.all_flags = Flags()
        term.matched_sources = ("app",)
        unit = Mock()
        unit.translation.language.uses_whitespace.return_value = True
        with patch("weblate.glossary.models.get_glossary_terms", return_value=[term]):
            check = GlossaryCheck()
            self.assertFalse(check.check_single("app", "appli", unit))
            self.assertEqual(check.check_single("app", "logiciel", unit), {"app"})
            self.assertEqual(check.check_single("app", "missing", unit), {"app"})
        term.all_flags = Flags("read-only")
        self.assertEqual(list(get_glossary_tuples([term])), [("app", "app")])


class TBXIntegrationTest(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.component = self.create_tbx()
        self.translation = self.component.translation_set.get(language_code="cs")
        filename = self.translation.get_filename()
        assert filename is not None
        self.filename = Path(filename)
        self.filename.write_bytes(TBX.replace(b'xml:lang="fr"', b'xml:lang="cs"'))
        self.sync()

    def sync(self) -> None:
        self.translation.drop_store_cache()
        self.component.unload_sources()
        self.translation.check_sync(force=True)
        self.unit = self.translation.unit_set.get(context="concept-example")
        self.translation.drop_store_cache()

    def test_import_edit_metadata_and_api(self) -> None:
        self.assertEqual(
            self.unit.get_target_plurals(), ["application", "appli", "logiciel"]
        )
        self.assertEqual(
            self.unit.source_unit.get_source_plurals(), ["application", "app"]
        )
        original_pk = self.unit.pk
        self.unit.translate(
            None, ["appli", "renamed", "logiciel"], STATE_TRANSLATED, propagate=False
        )
        self.unit.refresh_from_db()
        self.assertEqual(
            [term["id"] for term in self.unit.tbx_terms["target"]],
            [None, "target-full", "target-blocked"],
        )
        self.filename.write_bytes(
            self.filename.read_bytes().replace(b"Full name", b"Updated note")
        )
        self.sync()
        self.assertEqual(self.unit.pk, original_pk)
        self.assertEqual(
            self.unit.get_target_plurals(), ["appli", "renamed", "logiciel"]
        )
        self.assertEqual(
            self.unit.tbx_terms["target"][1]["notes"][-1]["text"], "Updated note"
        )
        data = UnitSerializer(
            self.unit, context={"request": RequestFactory().get("/")}
        ).data
        self.assertEqual(data["tbx_terms"], self.unit.tbx_terms)
        serializer = UnitSerializer(
            self.unit, data={"tbx_terms": {"target": []}}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("tbx_terms", serializer.validated_data)

    def test_editor_preserves_more_than_ten_alternatives(self) -> None:
        store = self.translation.store
        texts = [f"alternative {index}" for index in range(12)]
        store.content_units[0].set_target(texts)
        store.save()
        self.sync()
        original_records = deepcopy(self.unit.tbx_terms["target"])
        texts[0] = "edited first alternative"
        field = PluralField()
        data = {f"target_{index}": text for index, text in enumerate(texts)}
        target = field.clean(field.widget.value_from_datadict(data, {}, "target"))
        self.unit.translate(None, target, STATE_TRANSLATED, propagate=False)
        self.translation.commit_pending("test", None)
        self.sync()
        self.assertEqual(self.unit.get_target_plurals(), texts)
        self.assertEqual(self.unit.tbx_terms["target"][1:], original_records[1:])

    def test_alias_refresh_matches_sibling_language(self) -> None:
        self.component.is_glossary = True
        self.component.save()
        self.filename.with_name("fr.tbx").write_bytes(TBX)
        self.component.create_translations_immediate(force=True)
        sibling = self.component.translation_set.get(language_code="fr")
        self.filename.write_bytes(
            self.filename.read_bytes().replace(
                b"<term>app</term>", b"<term>new alias</term>"
            )
        )
        self.sync()
        # Only the Czech file was reparsed; the French unit still has the old text.
        self.assertEqual(
            sibling.unit_set.get(context="concept-example").get_source_plurals(),
            ["application", "app"],
        )
        sibling.refresh_from_db()
        edited = Unit(translation=sibling, source="new alias")
        matches = get_glossary_terms(edited, include_variants=False)
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            [record["text"] for record in matches[0].glossary_sources], ["new alias"]
        )
        self.assertEqual(
            list(get_glossary_tuples(matches)), [("new alias", "application")]
        )

    def test_glossary_term_direction(self) -> None:
        self.component.source_language = Language.objects.get(code="ar")
        self.translation.language = Language.objects.get(code="he")
        self.unit.translation = self.translation
        for readonly in (False, True):
            with self.subTest(readonly=readonly):
                self.unit.all_flags = Flags("read-only" if readonly else "")
                prepare_glossary_alternatives(self.unit)
                rendered = lxml_html.fromstring(
                    render_to_string(
                        "snippets/glossary-concept.html", {"item": self.unit}
                    )
                )
                sources = rendered.xpath('.//td[@class="source"]/div[@lang]')
                targets = rendered.xpath(".//button/span[@lang]")
                for elements, language in (
                    (sources, "ar"),
                    (targets, "ar" if readonly else "he"),
                ):
                    self.assertTrue(elements)
                    for element in elements:
                        self.assertEqual(element.get("lang"), language)
                        self.assertEqual(element.get("dir"), "rtl")
                        self.assertIn("bidi-isolate", element.get("class", ""))

    def test_single_source_term_note_rendered_once(self) -> None:
        self.filename.write_bytes(
            self.filename.read_bytes()
            .replace(b'<tig id="source-short"><term>app</term></tig>', b"")
            .replace(
                b"<term>application</term>",
                b'<term>application</term><note from="developer">Term note</note>',
                1,
            )
        )
        self.sync()
        self.assertEqual(self.unit.note, "Term note")
        self.unit.note += "\nAdditional developer note"
        prepare_glossary_alternatives(self.unit)
        rendered = render_to_string(
            "snippets/glossary-concept.html", {"item": self.unit}
        )
        self.assertEqual(rendered.count("Term note"), 1)
        self.assertEqual(rendered.count("Additional developer note"), 1)

    def test_generated_export_metadata_roundtrip(self) -> None:
        self.unit.all_flags = Flags("terminology, read-only, max-length:50")
        exporter = TBXExporter(
            translation=self.translation,
            project=self.component.project,
            language=self.translation.language,
            source_language=self.component.source_language,
        )
        exporter.add_unit(self.unit)
        content = exporter.serialize()
        restored: TBXUnit = TBXFormat(
            BytesIO(content), source_language="en", language_code="cs"
        ).content_units[0]
        self.assertEqual(restored.source, self.unit.source)
        self.assertEqual(restored.target, self.unit.target)
        self.assertEqual(restored.context, "concept-example")
        self.assertEqual(restored.tbx_terms, self.unit.tbx_terms)
        self.assertIn("terminology", restored.flags)
        self.assertIn("read-only", restored.flags)
        self.assertEqual(restored.flags.get_value("max-length"), 50)
        self.assertNotIn(b'xml:lang="de"', content)
        self.assertEqual(content.count(b"A program."), 1)

    def test_native_edit_preserves_other_language(self) -> None:
        store = self.translation.store
        wrapped = store.content_units[0]
        german = etree.tostring(wrapped.unit.get_target_dom("de"), with_tail=False)
        wrapped.set_target(["appli", "renamed", "logiciel"])
        wrapped.set_explanation("Czech explanation")
        store.save()
        self.sync()
        restored = self.translation.store.content_units[0]
        self.assertEqual(
            etree.tostring(restored.unit.get_target_dom("de"), with_tail=False), german
        )
        self.assertEqual(restored.explanation, "Czech explanation")
        self.assertNotIn("Czech explanation", restored.source_explanation)

    def test_single_concept_rendering(self) -> None:
        self.unit.matched_sources = ("app",)
        prepare_glossary_alternatives(self.unit)
        html = render_to_string(
            "snippets/glossary.html",
            {"glossary": [self.unit], "unit": self.unit, "user": get_anonymous()},
        )
        self.assertEqual(html.count('class="btn btn-link glossary-copy"'), 3)
        self.assertEqual(html.count('title="Edit glossary term"'), 1)
        self.assertIn('data-glossary-text="logiciel"', html)
        self.assertIn("disabled", html)

    def test_pending_source_edit_survives_metadata_refresh(self) -> None:
        source = self.unit.source_unit
        source.refresh_from_db()
        self.assertIn("tbx_terms", source.details)
        source.store_old_unit(source)
        source.store_disk_state()
        source.source = source.target = join_plural(["application", "edited alias"])
        source.explanation = "Pending explanation"
        source.details["tbx_terms"] = {
            side: reconcile_terms(
                source.tbx_terms[side], ["application", "edited alias"]
            )
            for side in ("source", "target")
        }
        source.save(only_save=True)
        self.filename.write_bytes(
            self.filename.read_bytes().replace(
                b'<tig id="source-short"><term>app</term>',
                b'<tig id="source-short"><term>app</term><note from="custom">New source note</note>',
            )
        )
        self.sync()
        source.refresh_from_db()
        self.assertEqual(source.get_source_plurals(), ["application", "edited alias"])
        self.assertEqual(source.target, source.source)
        self.assertEqual(source.explanation, "Pending explanation")
        self.assertEqual(source.tbx_terms["source"][1]["id"], "source-short")
        self.assertEqual(
            source.tbx_terms["source"][1]["notes"][-1]["text"], "New source note"
        )
        self.assertEqual(
            source.details["disk_state"]["tbx_terms"]["source"][1]["text"], "app"
        )

    def test_source_alias_refresh_updates_word_count_and_checks(self) -> None:
        source = self.unit.source_unit
        source.extra_flags = "max-length:20"
        source.save(only_save=True)
        words = source.num_words
        self.filename.write_bytes(
            self.filename.read_bytes().replace(
                b"<term>app</term>",
                b"<term>much longer alias...</term>",
            )
        )
        self.sync()
        source.refresh_from_db()
        self.assertGreater(source.num_words, words)
        self.assertTrue(source.check_set.filter(name="source-max-length").exists())
        self.filename.write_bytes(
            self.filename.read_bytes().replace(
                b"much longer alias...",
                b"app",
            )
        )
        self.sync()
        source.refresh_from_db()
        self.assertEqual(source.num_words, words)
        self.assertFalse(source.check_set.filter(name="source-max-length").exists())

    def test_scoped_notes_and_fuzzy_rendering(self) -> None:
        metadata = deepcopy(self.unit.tbx_terms)
        for side in ("source", "target"):
            for term in metadata[side]:
                term["notes"].extend(
                    [
                        {
                            "scope": "concept",
                            "origin": "custom",
                            "text": "Shared <concept>",
                        },
                        {
                            "scope": "language",
                            "origin": "custom",
                            "text": f"{side} language note",
                        },
                    ]
                )
        metadata["source"][1]["notes"].append(
            {"scope": "term", "origin": "custom", "text": "Source term note"}
        )
        self.unit.details["tbx_terms"] = metadata
        self.unit.state = STATE_FUZZY
        self.unit.source_unit.details["tbx_terms"] = {"source": metadata["source"]}
        prepare_glossary_alternatives(self.unit)
        rendered = render_to_string(
            "snippets/glossary-concept.html", {"item": self.unit}
        )
        for text in (
            "Shared &lt;concept&gt;",
            "source language note",
            "target language note",
            "Source term note",
            "A program.",
            "This translation needs editing.",
        ):
            self.assertEqual(rendered.count(text), 1, text)
        self.unit.state = STATE_TRANSLATED
        rendered = render_to_string(
            "snippets/glossary-concept.html", {"item": self.unit}
        )
        self.assertNotIn("This translation needs editing.", rendered)

    def test_term_information_list_semantics(self) -> None:
        rendered = lxml_html.fromstring(
            render_to_string("snippets/tbx-terms.html", {"unit": self.unit})
        )
        lists = rendered.findall(".//ul")
        self.assertEqual(len(lists), 2)
        for element in lists:
            self.assertTrue(all(child.tag == "li" for child in element))
            self.assertFalse((element.text or "").strip())
            self.assertTrue(all(not (child.tail or "").strip() for child in element))

    def test_export_metadata_content_order(self) -> None:
        self.unit.note = "Developer note"
        self.unit.explanation = "Target explanation"
        self.unit.source_unit.explanation = "Source explanation"
        self.unit.unresolved_comments = [Mock(comment="Review comment")]
        self.unit.suggestion_set.create(target="Suggested term")
        metadata = deepcopy(self.unit.tbx_terms)
        for side in ("source", "target"):
            for term in metadata[side]:
                term["notes"].extend(
                    [
                        {
                            "scope": "concept",
                            "origin": "custom",
                            "text": "Concept note",
                        },
                        {
                            "scope": "language",
                            "origin": "custom",
                            "text": f"{side} note",
                        },
                    ]
                )
        self.unit.details["tbx_terms"] = metadata
        exporter = TBXExporter(
            translation=self.translation,
            project=self.component.project,
            language=self.translation.language,
            source_language=self.component.source_language,
        )
        exporter.add_unit(self.unit)
        entry = etree.fromstring(exporter.serialize()).find(".//termEntry")
        assert entry is not None
        # Validate the TBX structural content models, including metadata before
        # langSet/tig and a term before its term metadata.
        schema = etree.DTD(
            StringIO("""
<!ELEMENT termEntry ((descrip|note)*,langSet+)>
<!ATTLIST termEntry id CDATA #IMPLIED weblate-flags CDATA #IMPLIED xmlns:xml CDATA #IMPLIED>
<!ELEMENT langSet ((descrip|note)*,tig+)>
<!ATTLIST langSet xml:lang CDATA #REQUIRED>
<!ELEMENT tig (term,(termNote|descrip|note)*)>
<!ATTLIST tig id CDATA #IMPLIED>
<!ELEMENT term (#PCDATA)>
<!ELEMENT termNote (#PCDATA)>
<!ATTLIST termNote type CDATA #IMPLIED>
<!ELEMENT descrip (#PCDATA)>
<!ATTLIST descrip type CDATA #IMPLIED>
<!ELEMENT note (#PCDATA)>
<!ATTLIST note type CDATA #IMPLIED from CDATA #IMPLIED>
""")
        )
        self.assertTrue(schema.validate(entry), str(schema.error_log))
