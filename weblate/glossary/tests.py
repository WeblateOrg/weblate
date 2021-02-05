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

from django.conf import settings
from django.urls import reverse

from weblate.addons.consistency import LangaugeConsistencyAddon
from weblate.glossary.models import get_glossary_terms
from weblate.trans.models import Unit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file

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
        self.glossary = self.glossary_component.add_new_language(
            self.get_translation().language,
            None,
        )

    @classmethod
    def _databases_support_transactions(cls):
        # This is workaroud for MySQL as FULL TEXT index does not work
        # well inside a transaction, so we avoid using transactions for
        # tests. Otherwise we end up with no matches for the query.
        # See https://dev.mysql.com/doc/refman/5.6/en/innodb-fulltext-index.html
        if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
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
        self.glossary.unit_set.create(
            source="hello",
            target="ahoj",
            id_hash=1,
            position=1,
        )
        self.glossary.unit_set.create(
            source="thank",
            target="děkujeme",
            id_hash=2,
            position=2,
        )
        unit = self.get_unit("Thank you for using Weblate.")
        self.assertEqual(get_glossary_terms(unit).count(), 1)
        self.glossary.unit_set.create(
            source="thank",
            target="díky",
            id_hash=3,
            position=3,
        )
        self.assertEqual(get_glossary_terms(unit).count(), 2)
        self.glossary.unit_set.create(
            source="thank you",
            target="děkujeme vám",
            id_hash=4,
            position=4,
        )
        self.assertEqual(get_glossary_terms(unit).count(), 3)
        self.glossary.unit_set.create(
            source="thank you for using Weblate",
            target="děkujeme vám za použití Weblate",
            id_hash=5,
            position=5,
        )
        self.assertEqual(get_glossary_terms(unit).count(), 4)

    def test_get_long(self):
        """Test parsing long source string."""
        unit = self.get_unit()
        unit.source = LONG
        unit.save()
        self.assertEqual(get_glossary_terms(unit).count(), 0)
        return unit

    def test_stoplist(self):
        unit = self.test_get_long()
        self.glossary.unit_set.create(
            source="the blue",
            target="modrý",
            id_hash=1,
            position=1,
        )
        self.glossary.unit_set.create(
            source="the red",
            target="červený",
            id_hash=2,
            position=2,
        )

        self.assertEqual(get_glossary_terms(unit).count(), 1)

    def test_get_dash(self):
        unit = self.get_unit("Thank you for using Weblate.")
        unit.source = "Nordrhein-Westfalen"
        self.glossary.unit_set.create(
            source="Nordrhein-Westfalen",
            target="Northrhine Westfalia",
            id_hash=1,
            position=1,
        )
        self.assertEqual(get_glossary_terms(unit).count(), 1)

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

    def test_terminology(self):
        start = Unit.objects.count()

        # Add single term
        self.test_add()

        # Verify it has been added to single language (+ source)
        unit = self.glossary_component.source_translation.unit_set.get(source="source")
        self.assertEqual(Unit.objects.count(), start + 2)
        self.assertEqual(unit.unit_set.count(), 2)

        # Enable language consistency
        LangaugeConsistencyAddon.create(self.glossary_component)
        self.assertEqual(unit.unit_set.count(), 2)
        self.assertEqual(Unit.objects.count(), start + 2)

        # Make it terminology
        unit.extra_flags = "terminology"
        unit.save()

        # Verify it has been added to all languages
        self.assertEqual(Unit.objects.count(), start + 4)
        self.assertEqual(unit.unit_set.count(), 4)
