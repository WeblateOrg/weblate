# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for glossary manipulations."""

from __future__ import annotations

import csv
import json
from io import StringIO

from django.db import transaction
from django.urls import reverse

from weblate.glossary.models import get_glossary_terms, get_glossary_tsv
from weblate.glossary.tasks import (
    cleanup_stale_glossaries,
    sync_terminology,
)
from weblate.lang.models import Language
from weblate.trans.models import Translation, Unit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.db import TransactionsTestMixin
from weblate.utils.hash import calculate_hash
from weblate.utils.state import STATE_READONLY, STATE_TRANSLATED

TEST_TBX = get_test_file("terms.tbx")
TEST_CSV = get_test_file("terms.csv")
TEST_CSV_HEADER = get_test_file("terms-header.csv")
TEST_PO = get_test_file("terms.po")

LONG = """

<div><b>Game Settings</b> can be found by pressing your device's
Menu Button.</div>

<p>________________</p>
<h1>Interface Icons</h1>

<div><b>The Chest</b><img alt=chest src=chest.png /></div>
<p>Quickslots [Long press the pouches inside to assign items for instant
use]</p>

<div><b>The Hero</b><img alt=hero src=char_hero.png /></div>
<p>Menu [Overview, Quests, Skills &amp; Inventory *]</p>
<p>* (While in inventory, press an item for information &amp; long press for
more options)</p>

<div><b>The Enemy</b><img alt=monster src=monster.png /></div>
<p>Information [Appears during Combat]</p>



<p>________________</p>
<h1>Combat</h1>

<p>Actions taken during battle cost AP...</p>

<div><b>Attacking</b> - [3AP] *</div>
<img alt=attacking src=doubleattackexample.png />
<p>* (Equipping Gear &amp; Using Items may alter AP &amp; usage cost)</p>

<div><b>Using Items</b> - [5AP]</div>
<div><b>Fleeing</b> - [6AP]</div>



<p>________________</p>
<h1>Advanced Combat</h1>

<div>During Combat, long press a tile adjacent to the Hero...</div>

<div><b>To Flee</b></div>
<p>(chosen tile is highlighted - Attack Button changes to Move)</p>
<img alt=flee src=flee_example.png />
<p>[flee mode activated - Long press enemy to re-enter combat]</p>

<div><b>To Change Targets</b></div>
<p>(the red target highlight shifts between enemies)</p>
<p>[the target has been changed]</p>

"""


def unit_sources_and_positions(units):
    return {(unit.source, unit.glossary_positions) for unit in units}


class GlossaryTest(TransactionsTestMixin, ViewTestCase):
    """Testing of glossary manipulations."""

    CREATE_GLOSSARIES: bool = True

    def setUp(self) -> None:
        super().setUp()
        self.glossary_component = self.project.glossaries[0]
        self.glossary = self.glossary_component.translation_set.get(
            language=self.get_translation().language
        )

    def import_file(self, filename, **kwargs):
        with open(filename, "rb") as handle:
            params = {"file": handle, "method": "add"}
            params.update(kwargs)
            return self.client.post(
                reverse("upload", kwargs={"path": self.glossary.get_url_path()}),
                params,
            )

    def add_term(self, source, target, context="") -> None:
        id_hash = calculate_hash(source, context)
        source_unit = self.glossary_component.source_translation.unit_set.create(
            source=source,
            target=source,
            context=context,
            id_hash=id_hash,
            position=1,
            state=STATE_TRANSLATED,
        )
        self.glossary.unit_set.create(
            source=source,
            target=target,
            context=context,
            source_unit=source_unit,
            id_hash=id_hash,
            position=1,
            state=STATE_TRANSLATED,
        )
        self.glossary.invalidate_cache()

    def test_import(self) -> None:
        """Test for importing of TBX into glossary."""

        def change_term() -> None:
            term = self.glossary.unit_set.get(target="podpůrná vrstva")
            term.target = "zkouška sirén"
            term.save()

        show_url = self.glossary.get_absolute_url()

        # Import file
        response = self.import_file(TEST_TBX)

        # Check correct response
        self.assertRedirects(response, show_url)

        # Check number of imported objects
        self.assertEqual(self.glossary.unit_set.count(), 164)

        # Change single term
        change_term()

        # Import file again with orverwriting
        response = self.import_file(
            TEST_TBX, method="translate", conflicts="replace-translated"
        )

        # Check number of imported objects
        self.assertEqual(self.glossary.unit_set.count(), 164)
        self.assertTrue(
            self.glossary.unit_set.filter(target="podpůrná vrstva").exists()
        )

        # Change single term
        change_term()

        # Import file again with adding
        response = self.import_file(TEST_TBX)

        # Check number of imported objects
        self.assertEqual(self.glossary.unit_set.count(), 164)

        self.assertFalse(
            self.glossary.unit_set.filter(target="podpůrná vrstva").exists()
        )

    def test_import_csv(self) -> None:
        # Import file
        response = self.import_file(TEST_CSV)

        # Check correct response
        self.assertRedirects(response, self.glossary.get_absolute_url())

        response = self.client.get(self.glossary.get_absolute_url())

        # Check number of imported objects
        self.assertEqual(self.glossary.unit_set.count(), 163)

    def test_import_csv_header(self) -> None:
        # Import file
        response = self.import_file(TEST_CSV_HEADER)

        # Check correct response
        self.assertRedirects(response, self.glossary.get_absolute_url())

        # Check number of imported objects
        self.assertEqual(self.glossary.unit_set.count(), 163)

    def test_import_po(self) -> None:
        # Import file
        response = self.import_file(TEST_PO)

        # Check correct response
        self.assertRedirects(response, self.glossary.get_absolute_url())

        # Check number of imported objects
        self.assertEqual(self.glossary.unit_set.count(), 164)

    def test_get_terms(self) -> None:
        self.add_term("hello", "ahoj")
        self.add_term("thank", "děkujeme")

        unit = self.get_unit("Thank you for using Weblate.")
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)), {("thank", ((0, 5),))}
        )
        self.add_term("thank", "díky", "other")
        unit.glossary_terms = None
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)), {("thank", ((0, 5),))}
        )
        self.add_term("thank you", "děkujeme vám")
        unit.glossary_terms = None
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)),
            {
                ("thank", ((0, 5),)),
                ("thank you", ((0, 9),)),
            },
        )
        self.add_term("thank you for using Weblate", "děkujeme vám za použití Weblate")
        unit.glossary_terms = None
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)),
            {
                ("thank", ((0, 5),)),
                ("thank you", ((0, 9),)),
                ("thank you for using Weblate", ((0, 27),)),
            },
        )
        self.add_term("web", "web")
        unit.glossary_terms = None
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)),
            {
                ("thank", ((0, 5),)),
                ("thank you", ((0, 9),)),
                ("thank you for using Weblate", ((0, 27),)),
            },
        )

    def test_substrings(self) -> None:
        self.add_term("reach", "dojet")
        self.add_term("breach", "prolomit")
        unit = self.get_unit()
        unit.source = "Reach summit"
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)), {("reach", ((0, 5),))}
        )

    def test_phrases(self) -> None:
        self.add_term("Destructive Breach", "x")
        self.add_term("Flame Breach", "x")
        self.add_term("Frost Breach", "x")
        self.add_term("Icereach", "x")
        self.add_term("Reach", "x")
        self.add_term("Reachable", "x")
        self.add_term("Skyreach", "x")
        unit = self.get_unit()
        unit.source = "During invasion from the Reach. Town burn, prior records lost.\n"
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)),
            {("Reach", ((25, 30),))},
        )
        self.add_term("Town", "x")
        unit.glossary_terms = None
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)),
            {
                ("Town", ((32, 36),)),
                ("Reach", ((25, 30),)),
            },
        )
        self.add_term("The Reach", "x")
        unit.glossary_terms = None
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)),
            {("Town", ((32, 36),)), ("Reach", ((25, 30),)), ("The Reach", ((21, 30),))},
        )

    def get_long_unit(self):
        unit = self.get_unit()
        unit.source = LONG
        unit.save()
        return unit

    def test_get_long(self) -> None:
        """Test parsing long source string."""
        unit = self.get_long_unit()
        self.assertEqual(unit_sources_and_positions(get_glossary_terms(unit)), set())

    def test_stoplist(self) -> None:
        unit = self.get_long_unit()
        self.add_term("the blue", "modrý")
        self.add_term("the red", "červený")
        unit.glossary_terms = None

        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)),
            {("the red", ((1287, 1294),))},
        )

    def test_get_dash(self) -> None:
        unit = self.get_unit("Thank you for using Weblate.")
        unit.source = "Nordrhein-Westfalen"
        self.add_term("Nordrhein-Westfalen", "Northrhine Westfalia")
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)),
            {("Nordrhein-Westfalen", ((0, 19),))},
        )

    def test_get_single(self) -> None:
        unit = self.get_unit("Thank you for using Weblate.")
        unit.source = "thank"
        self.add_term("thank", "díky")
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)), {("thank", ((0, 5),))}
        )

    def test_get_newline(self) -> None:
        unit = self.get_unit("Thank you for using Weblate.")
        unit.source = "Thank you for using Weblate.\nThank you again."
        self.add_term("thank", "díky")
        self.assertEqual(
            unit_sources_and_positions(get_glossary_terms(unit)),
            {("thank", ((0, 5), (29, 34)))},
        )

    def do_add_unit(
        self, language: str = "cs", expected_status: int = 200, **kwargs
    ) -> None:
        unit = self.get_unit("Thank you for using Weblate.", language=language)
        glossary = self.glossary_component.translation_set.get(
            language=unit.translation.language
        )
        # Add term
        response = self.client.post(
            reverse("js-add-glossary", kwargs={"unit_id": unit.pk}),
            {
                "context": "context",
                "source_0": "source",
                "target_0": "překlad",
                "translation": glossary.pk,
                "auto_context": 1,
                **kwargs,
            },
        )
        content = response.json()
        self.assertEqual(content["responseCode"], expected_status)

    def test_add(self) -> None:
        """Test for adding term from translate page."""
        start = Unit.objects.count()
        self.do_add_unit()
        # Should be added to the source and translation only
        self.assertEqual(Unit.objects.count(), start + 2)

    def test_add_terminology(self) -> None:
        start = Unit.objects.count()
        self.do_add_unit(expected_status=403, terminology=1)
        self.make_manager()
        self.do_add_unit(terminology=1)
        # Should be added to all languages
        self.assertEqual(Unit.objects.count(), start + 4)

    def test_add_untranslatable(self) -> None:
        start = Unit.objects.count()
        self.do_add_unit(read_only=1)
        # Should be added to all languages
        self.assertEqual(Unit.objects.count(), start + 2)
        unit = Unit.objects.get(source="source", translation__language__code="cs")
        self.assertEqual(unit.state, STATE_READONLY)
        self.assertEqual(unit.target, "")

    def test_add_terminology_existing(self) -> None:
        self.make_manager()
        start = Unit.objects.count()
        # Add unit to other translation
        self.do_add_unit(language="it")
        # Add terminology to translation where unit does not exist
        self.do_add_unit(terminology=1)
        # Should be added to all languages
        self.assertEqual(Unit.objects.count(), start + 4)

    def test_add_duplicate(self) -> None:
        self.do_add_unit()
        self.do_add_unit()

    def test_terminology(self) -> None:
        start = Unit.objects.count()

        # Add single term
        self.do_add_unit()

        # Verify it has been added to single language (+ source)
        unit = self.glossary_component.source_translation.unit_set.get(source="source")
        self.assertEqual(Unit.objects.count(), start + 2)
        self.assertEqual(unit.unit_set.count(), 2)

        # Enable language consistency
        self.assertEqual(unit.unit_set.count(), 2)
        self.assertEqual(Unit.objects.count(), start + 2)

        # Make it terminology
        with transaction.atomic():
            unit.translation.component.unload_sources()
            unit.extra_flags = "terminology"
            unit.save()

        # Verify it has been added to all languages
        self.assertEqual(Unit.objects.count(), start + 4)
        self.assertEqual(unit.unit_set.count(), 4)

        # Terminology sync should be no-op now
        sync_terminology(unit.translation.component.id, unit.translation.component)
        self.assertEqual(Unit.objects.count(), start + 4)
        self.assertEqual(unit.unit_set.count(), 4)

    def test_terminology_explanation_sync(self) -> None:
        self.make_manager()
        unit = self.get_unit("Thank you for using Weblate.")
        # Add terms
        response = self.client.post(
            reverse("js-add-glossary", kwargs={"unit_id": unit.pk}),
            {
                "source_0": "source 1",
                "target_0": "target 1",
                "translation": self.glossary.pk,
                "explanation": "explained 1",
                "terminology": "1",
                "auto_context": 1,
            },
        )
        content = json.loads(response.content.decode())
        self.assertEqual(content["responseCode"], 200)

        response = self.client.post(
            reverse("js-add-glossary", kwargs={"unit_id": unit.pk}),
            {
                "source_0": "source 2",
                "target_0": "target 2",
                "translation": self.glossary.pk,
                "explanation": "explained 2",
                "terminology": "1",
                "auto_context": 1,
            },
        )
        content = json.loads(response.content.decode())
        self.assertEqual(content["responseCode"], 200)

        glossary_units = Unit.objects.filter(
            translation__component=self.glossary.component
        )

        self.assertEqual(self.glossary.unit_set.count(), 2)
        self.assertEqual(
            glossary_units.count(), 2 * self.glossary.component.translation_set.count()
        )

        self.assertEqual(
            set(
                glossary_units.filter(translation__language_code="cs").values_list(
                    "explanation", flat=True
                )
            ),
            {"explained 1", "explained 2"},
        )
        self.assertEqual(
            set(
                glossary_units.filter(translation__language_code="en").values_list(
                    "explanation", flat=True
                )
            ),
            {""},
        )

    def test_tsv(self) -> None:
        # Import file
        self.import_file(TEST_CSV)

        tsv_data = get_glossary_tsv(self.get_translation())

        handle = StringIO(tsv_data)

        reader = csv.reader(handle, "excel-tab")
        lines = list(reader)
        self.assertEqual(len(lines), 163)
        self.assertTrue(all(len(line) == 2 for line in lines))

    def test_stale_glossaries_cleanup(self) -> None:
        # setup: make glossary managed outside weblate
        self.glossary_component.repo = "git://example.com/test/project.git"
        self.glossary_component.save()

        initial_count = self.glossary_component.translation_set.count()

        # check glossary not deleted because it has a valid translation
        cleanup_stale_glossaries(self.project.id)
        self.assertEqual(self.glossary_component.translation_set.count(), initial_count)

        # delete translation: should trigger cleanup_stale_glossary task
        german = Language.objects.get(code="de")
        self.component.translation_set.get(language=german).remove(self.user)

        cleanup_stale_glossaries(self.project.id)
        self.assertEqual(self.glossary_component.translation_set.count(), initial_count)

        # make glossary managed by weblate
        self.glossary_component.repo = "local:"
        self.glossary_component.save()

        # check that one glossary has been deleted
        cleanup_stale_glossaries(self.project.id)
        self.assertEqual(
            self.glossary_component.translation_set.count(), initial_count - 1
        )

    def test_prohibited_initial_character(self) -> None:
        """Test that a prohibited initial character in views."""
        self.make_manager()
        response = self.client.post(
            reverse("new-unit", kwargs={"path": self.glossary.get_url_path()}),
            {
                "source_0": "=prohibited",
                "target_0": "target",
                "terminology": "on",
                "new-unit-form-type": "singular",
            },
            follow=True,
        )
        self.assertContains(response, "Prohibited initial character")
        self.assertContains(response, "New string has been added.")

        # add ignore flag, check warning is gone
        unit = self.glossary.unit_set.get(source="=prohibited")
        response = self.client.post(
            reverse("edit_context", kwargs={"pk": unit.pk}),
            {
                "next": reverse("translate", kwargs={"path": unit.get_url_path()}),
                "explanation": "",
                "extra_flags": "terminology,ignore-prohibited-initial-character",
            },
            follow=True,
        )
        self.assertNotContains(response, "Prohibited initial character")

    def removal_test(self, translation: Translation, *, commit: bool = False) -> None:
        self.assertEqual(translation.unit_set.count(), 0)
        self.add_term("hello", "ahoj")
        if commit:
            self.glossary_component.commit_pending("test", None)
        self.assertEqual(translation.unit_set.count(), 1)
        unit = translation.unit_set.get(source="hello")
        translation.delete_unit(None, unit)
        self.assertEqual(translation.unit_set.count(), 0)
        self.assertEqual(self.glossary_component.source_translation.unit_set.count(), 0)

    def test_string_removal(self) -> None:
        self.removal_test(self.glossary)

    def test_source_string_removal(self) -> None:
        self.removal_test(self.glossary_component.source_translation)

    def test_string_removal_commmit(self) -> None:
        self.removal_test(self.glossary, commit=True)

    def test_source_string_removal_commit(self) -> None:
        self.removal_test(self.glossary_component.source_translation, commit=True)
