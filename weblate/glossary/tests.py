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

"""Test for glossary manipulations."""

import json

from django.urls import reverse

from weblate.glossary.models import get_glossary_terms
from weblate.trans.models import Unit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.db import using_postgresql
from weblate.utils.hash import calculate_hash
from weblate.utils.state import STATE_TRANSLATED

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


class GlossaryTest(ViewTestCase):
    """Testing of glossary manipulations."""

    def setUp(self):
        super().setUp()
        self.glossary_component = self.project.glossaries[0]
        self.glossary = self.glossary_component.translation_set.get(
            language=self.get_translation().language
        )

    @classmethod
    def _databases_support_transactions(cls):
        # This is workaroud for MySQL as FULL TEXT index does not work
        # well inside a transaction, so we avoid using transactions for
        # tests. Otherwise we end up with no matches for the query.
        # See https://dev.mysql.com/doc/refman/5.6/en/innodb-fulltext-index.html
        if not using_postgresql():
            return False
        return super()._databases_support_transactions()

    def import_file(self, filename, **kwargs):
        with open(filename, "rb") as handle:
            params = {"file": handle, "method": "add"}
            params.update(kwargs)
            return self.client.post(
                reverse(
                    "upload_translation", kwargs=self.glossary.get_reverse_url_kwargs()
                ),
                params,
            )

    def add_term(self, source, target, context=""):
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

    def test_import(self):
        """Test for importing of TBX into glossary."""

        def change_term():
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

    def test_import_csv(self):
        # Import file
        response = self.import_file(TEST_CSV)

        # Check correct response
        self.assertRedirects(response, self.glossary.get_absolute_url())

        response = self.client.get(self.glossary.get_absolute_url())

        # Check number of imported objects
        self.assertEqual(self.glossary.unit_set.count(), 163)

    def test_import_csv_header(self):
        # Import file
        response = self.import_file(TEST_CSV_HEADER)

        # Check correct response
        self.assertRedirects(response, self.glossary.get_absolute_url())

        # Check number of imported objects
        self.assertEqual(self.glossary.unit_set.count(), 163)

    def test_import_po(self):
        # Import file
        response = self.import_file(TEST_PO)

        # Check correct response
        self.assertRedirects(response, self.glossary.get_absolute_url())

        # Check number of imported objects
        self.assertEqual(self.glossary.unit_set.count(), 164)

    def test_get_terms(self):
        self.add_term("hello", "ahoj")
        self.add_term("thank", "děkujeme")

        unit = self.get_unit("Thank you for using Weblate.")
        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)), {"thank"}
        )
        self.add_term("thank", "díky", "other")
        unit.glossary_terms = None
        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)), {"thank"}
        )
        self.add_term("thank you", "děkujeme vám")
        unit.glossary_terms = None
        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)),
            {"thank", "thank you"},
        )
        self.add_term("thank you for using Weblate", "děkujeme vám za použití Weblate")
        unit.glossary_terms = None
        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)),
            {"thank", "thank you", "thank you for using Weblate"},
        )
        self.add_term("web", "web")
        unit.glossary_terms = None
        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)),
            {"thank", "thank you", "thank you for using Weblate"},
        )

    def test_substrings(self):
        self.add_term("reach", "dojet")
        self.add_term("breach", "prolomit")
        unit = self.get_unit()
        unit.source = "Reach summit"
        self.assertEqual(
            list(get_glossary_terms(unit).values_list("source", flat=True)), ["reach"]
        )

    def test_phrases(self):
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
            list(get_glossary_terms(unit).values_list("source", flat=True)), ["Reach"]
        )
        self.add_term("Town", "x")
        unit.glossary_terms = None
        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)),
            {"Reach", "Town"},
        )
        self.add_term("The Reach", "x")
        unit.glossary_terms = None
        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)),
            {"Reach", "The Reach", "Town"},
        )

    def test_get_long(self):
        """Test parsing long source string."""
        unit = self.get_unit()
        unit.source = LONG
        unit.save()
        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)), set()
        )
        return unit

    def test_stoplist(self):
        unit = self.test_get_long()
        self.add_term("the blue", "modrý")
        self.add_term("the red", "červený")
        unit.glossary_terms = None

        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)), {"the red"}
        )

    def test_get_dash(self):
        unit = self.get_unit("Thank you for using Weblate.")
        unit.source = "Nordrhein-Westfalen"
        self.add_term("Nordrhein-Westfalen", "Northrhine Westfalia")
        self.assertEqual(
            set(get_glossary_terms(unit).values_list("source", flat=True)),
            {"Nordrhein-Westfalen"},
        )

    def test_add(self):
        """Test for adding term from translate page."""
        unit = self.get_unit("Thank you for using Weblate.")
        # Add term
        response = self.client.post(
            reverse("js-add-glossary", kwargs={"unit_id": unit.pk}),
            {"source": "source", "target": "překlad", "translation": self.glossary.pk},
        )
        content = json.loads(response.content.decode())
        self.assertEqual(content["responseCode"], 200)

    def test_add_duplicate(self):
        self.test_add()
        self.test_add()

    def test_terminology(self):
        start = Unit.objects.count()

        # Add single term
        self.test_add()

        # Verify it has been added to single language (+ source)
        unit = self.glossary_component.source_translation.unit_set.get(source="source")
        self.assertEqual(Unit.objects.count(), start + 2)
        self.assertEqual(unit.unit_set.count(), 2)

        # Enable language consistency
        self.assertEqual(unit.unit_set.count(), 2)
        self.assertEqual(Unit.objects.count(), start + 2)

        # Make it terminology
        unit.translation.component.unload_sources()
        unit.extra_flags = "terminology"
        unit.save()

        # Verify it has been added to all languages
        self.assertEqual(Unit.objects.count(), start + 4)
        self.assertEqual(unit.unit_set.count(), 4)
