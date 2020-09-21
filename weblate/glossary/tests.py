#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from weblate.glossary.models import Glossary, Term
from weblate.lang.models import get_english_lang
from weblate.trans.tests.test_views import FixtureTestCase
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


class GlossaryTest(FixtureTestCase):
    """Testing of glossary manipulations."""

    def setUp(self):
        super().setUp()
        self.glossary = Glossary.objects.create(
            name=self.project.name, color="silver", project=self.project
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

    def get_url(self, url, **kwargs):
        kwargs.update({"lang": "cs", "project": self.component.project.slug})
        return reverse(url, kwargs=kwargs)

    def import_file(self, filename, **kwargs):
        with open(filename, "rb") as handle:
            params = {"file": handle, "glossary": self.glossary.pk}
            params.update(kwargs)
            return self.client.post(self.get_url("upload_glossary"), params)

    def test_import(self):
        """Test for importing of TBX into glossary."""
        show_url = self.get_url("show_glossary")

        # Import file
        response = self.import_file(TEST_TBX)

        # Check correct response
        self.assertRedirects(response, show_url)

        # Check number of imported objects
        self.assertEqual(Term.objects.count(), 164)

        # Check they are shown
        response = self.client.get(show_url)
        self.assertContains(response, "podpůrná vrstva")

        # Change single term
        term = Term.objects.get(target="podpůrná vrstva")
        term.target = "zkouška sirén"
        term.save()

        # Import file again with orverwriting
        response = self.import_file(TEST_TBX, method="overwrite")

        # Check number of imported objects
        self.assertEqual(Term.objects.count(), 164)

        # Check entry got overwritten
        response = self.client.get(show_url)
        self.assertContains(response, "podpůrná vrstva")

        # Change single term
        term = Term.objects.get(target="podpůrná vrstva")
        term.target = "zkouška sirén"
        term.save()

        # Import file again with adding
        response = self.import_file(TEST_TBX, method="add")

        # Check number of imported objects
        self.assertEqual(Term.objects.count(), 165)

    def test_import_csv(self):
        # Import file
        response = self.import_file(TEST_CSV)

        # Check correct response
        self.assertRedirects(response, self.get_url("show_glossary"))

        response = self.client.get(self.get_url("show_glossary"))

        # Check number of imported objects
        self.assertEqual(Term.objects.count(), 163)

    def test_import_csv_header(self):
        # Import file
        response = self.import_file(TEST_CSV_HEADER)

        # Check correct response
        self.assertRedirects(response, self.get_url("show_glossary"))

        # Check number of imported objects
        self.assertEqual(Term.objects.count(), 163)

    def test_import_po(self):
        # Import file
        response = self.import_file(TEST_PO)

        # Check correct response
        self.assertRedirects(response, self.get_url("show_glossary"))

        # Check number of imported objects
        self.assertEqual(Term.objects.count(), 164)

    def test_edit(self):
        """Test for manually adding terms to glossary."""
        show_url = self.get_url("show_glossary")

        # Add term
        response = self.client.post(
            show_url,
            {"source": "source", "target": "překlad", "glossary": self.glossary.pk},
        )

        # Check correct response
        self.assertRedirects(response, show_url)

        # Check number of objects
        self.assertEqual(Term.objects.count(), 1)

        dict_id = Term.objects.all()[0].id
        edit_url = reverse("edit_glossary", kwargs={"pk": dict_id})

        # Check they are shown
        response = self.client.get(show_url)
        self.assertContains(response, "překlad")

        # Edit page
        response = self.client.get(edit_url)
        self.assertContains(response, "překlad")

        # Edit translation
        response = self.client.post(
            edit_url, {"source": "src", "target": "přkld", "glossary": self.glossary.pk}
        )
        self.assertRedirects(response, show_url)

        # Check they are shown
        response = self.client.get(show_url)
        self.assertContains(response, "přkld")

        # Test deleting
        delete_url = reverse("delete_glossary", kwargs={"pk": dict_id})
        response = self.client.post(delete_url)
        self.assertRedirects(response, show_url)

        # Check number of objects
        self.assertEqual(Term.objects.count(), 0)

    def test_download_csv(self):
        """Test for downloading CVS file."""
        # Import test data
        self.import_file(TEST_TBX)

        response = self.client.get(self.get_url("download_glossary"), {"format": "csv"})
        self.assertContains(response, '"addon","doplněk"')

    def test_download_tbx(self):
        """Test for downloading TBX file."""
        # Import test data
        self.import_file(TEST_TBX)

        response = self.client.get(self.get_url("download_glossary"), {"format": "tbx"})
        self.assertContains(response, "<term>website</term>")
        self.assertContains(response, "<term>webové stránky</term>")

    def test_download_xliff(self):
        """Test for downloading XLIFF file."""
        # Import test data
        self.import_file(TEST_TBX)

        response = self.client.get(
            self.get_url("download_glossary"), {"format": "xliff"}
        )
        self.assertContains(response, "<source>website</source>")
        self.assertContains(
            response, '<target state="translated">webové stránky</target>'
        )

    def test_download_po(self):
        """Test for downloading PO file."""
        # Import test data
        self.import_file(TEST_TBX)

        response = self.client.get(self.get_url("download_glossary"), {"format": "po"})
        self.assertContains(response, 'msgid "wizard"\nmsgstr "průvodce"')

    def test_list(self):
        """Test for listing glossaries."""
        self.import_file(TEST_TBX)

        # List glossaries
        response = self.client.get(reverse("show_glossaries", kwargs=self.kw_project))
        self.assertContains(response, "Czech")
        self.assertContains(response, "Italian")

        dict_url = self.get_url("show_glossary")

        # List all terms
        response = self.client.get(dict_url)
        self.assertContains(response, "Czech")
        self.assertContains(response, "1 / 2")
        self.assertContains(response, "datový tok")

        # Filtering by letter
        response = self.client.get(dict_url, {"letter": "b"})
        self.assertContains(response, "Czech")
        self.assertNotContains(response, "1 / 1")
        self.assertContains(response, "datový tok")

        # Filtering by string
        response = self.client.get(dict_url, {"term": "bookmark"})
        self.assertContains(response, "Czech")
        self.assertNotContains(response, "1 / 1")
        self.assertContains(response, "záložka")

    def test_get_terms(self):
        translation = self.get_translation()
        Term.objects.create(
            self.user,
            glossary=self.glossary,
            language=translation.language,
            source="hello",
            target="ahoj",
        )
        Term.objects.create(
            self.user,
            glossary=self.glossary,
            language=translation.language,
            source="thank",
            target="děkujeme",
        )
        unit = self.get_unit("Thank you for using Weblate.")
        self.assertEqual(Term.objects.get_terms(unit).count(), 1)
        Term.objects.create(
            self.user,
            glossary=self.glossary,
            language=translation.language,
            source="thank",
            target="díky",
        )
        self.assertEqual(Term.objects.get_terms(unit).count(), 2)
        Term.objects.create(
            self.user,
            glossary=self.glossary,
            language=translation.language,
            source="thank you",
            target="děkujeme vám",
        )
        self.assertEqual(Term.objects.get_terms(unit).count(), 3)
        Term.objects.create(
            self.user,
            glossary=self.glossary,
            language=translation.language,
            source="thank you for using Weblate",
            target="děkujeme vám za použití Weblate",
        )
        self.assertEqual(Term.objects.get_terms(unit).count(), 4)

    def test_get_long(self):
        """Test parsing long source string."""
        unit = self.get_unit()
        unit.source = LONG
        unit.save()
        self.assertEqual(Term.objects.get_terms(unit).count(), 0)
        return unit

    def test_stoplist(self):
        unit = self.test_get_long()
        # Add one matching and one not matching terms
        translation = self.get_translation()
        Term.objects.create(
            self.user,
            glossary=self.glossary,
            language=translation.language,
            source="the blue",
            target="modrý",
        )
        Term.objects.create(
            self.user,
            glossary=self.glossary,
            language=translation.language,
            source="the red",
            target="červený",
        )

        self.assertEqual(Term.objects.get_terms(unit).count(), 1)

    def test_get_dash(self):
        translation = self.get_translation()
        unit = self.get_unit("Thank you for using Weblate.")
        unit.source = "Nordrhein-Westfalen"
        Term.objects.create(
            self.user,
            glossary=self.glossary,
            language=translation.language,
            source="Nordrhein-Westfalen",
            target="Northrhine Westfalia",
        )
        self.assertEqual(Term.objects.get_terms(unit).count(), 1)

    def test_add(self):
        """Test for adding term from translate page."""
        unit = self.get_unit("Thank you for using Weblate.")
        # Add term
        response = self.client.post(
            reverse("js-add-glossary", kwargs={"unit_id": unit.pk}),
            {"source": "source", "target": "překlad", "glossary": self.glossary.pk},
        )
        content = json.loads(response.content.decode())
        self.assertEqual(content["responseCode"], 200)

    def test_manage(self):
        url = reverse("show_glossaries", kwargs=self.kw_project)
        self.assertEqual(Glossary.objects.count(), 1)

        # No permission to create
        self.client.post(url, {"name": "GlossaryName", "color": "navy"})
        self.assertEqual(Glossary.objects.count(), 1)

        # Get permissions
        self.user.is_superuser = True
        self.user.save()

        # Create, missing param
        response = self.client.post(url, {"name": "Name"})
        self.assertContains(response, "This field is required.")

        # Create
        self.client.post(
            url,
            {
                "name": "GlossaryName",
                "color": "navy",
                "source_language": get_english_lang(),
            },
        )
        self.assertEqual(Glossary.objects.count(), 2)

        glossary = Glossary.objects.get(name="GlossaryName")

        # Edit, wrong object
        response = self.client.post(url, {"name": "Name", "edit_glossary": -2})
        self.assertContains(response, "Glossary was not found.")

        # Edit, missing param
        response = self.client.post(url, {"name": "Name", "edit_glossary": glossary.pk})
        self.assertContains(response, "This field is required.")

        # Edit
        self.client.post(
            url,
            {
                "name": "OtherName",
                "color": "navy",
                "source_language": get_english_lang(),
                "edit_glossary": glossary.pk,
            },
        )
        glossary.refresh_from_db()
        self.assertEqual(glossary.name, "OtherName")

        # Delete
        self.client.post(url, {"delete_glossary": glossary.pk})
        self.assertEqual(Glossary.objects.count(), 1)

        # Delete, wrong object
        response = self.client.post(url, {"delete_glossary": -2})
        self.assertContains(response, "Glossary was not found.")
