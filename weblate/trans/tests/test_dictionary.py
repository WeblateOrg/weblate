# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

"""Test for dictionary manipulations."""

from __future__ import unicode_literals

import json

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.models import Dictionary
from weblate.trans.tests.utils import get_test_file

TEST_TBX = get_test_file('terms.tbx')
TEST_CSV = get_test_file('terms.csv')
TEST_CSV_HEADER = get_test_file('terms-header.csv')
TEST_PO = get_test_file('terms.po')

LONG = '''

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

'''


class DictionaryTest(FixtureTestCase):
    """Testing of dictionary manipulations."""

    def get_url(self, url, **kwargs):
        kwargs.update({
            'lang': 'cs',
            'project': self.component.project.slug,
        })
        return reverse(url, kwargs=kwargs)

    def import_file(self, filename, **kwargs):
        with open(filename, 'rb') as handle:
            params = {'file': handle}
            params.update(kwargs)
            return self.client.post(
                self.get_url('upload_dictionary'),
                params
            )

    def test_import(self):
        """Test for importing of TBX into glossary."""
        show_url = self.get_url('show_dictionary')

        # Import file
        response = self.import_file(TEST_TBX)

        # Check correct response
        self.assertRedirects(response, show_url)

        # Check number of imported objects
        self.assertEqual(Dictionary.objects.count(), 164)

        # Check they are shown
        response = self.client.get(show_url)
        self.assertContains(response, 'podpůrná vrstva')

        # Change single word
        word = Dictionary.objects.get(target='podpůrná vrstva')
        word.target = 'zkouška sirén'
        word.save()

        # Import file again with orverwriting
        response = self.import_file(TEST_TBX, method='overwrite')

        # Check number of imported objects
        self.assertEqual(Dictionary.objects.count(), 164)

        # Check entry got overwritten
        response = self.client.get(show_url)
        self.assertContains(response, 'podpůrná vrstva')

        # Change single word
        word = Dictionary.objects.get(target='podpůrná vrstva')
        word.target = 'zkouška sirén'
        word.save()

        # Import file again with adding
        response = self.import_file(TEST_TBX, method='add')

        # Check number of imported objects
        self.assertEqual(Dictionary.objects.count(), 165)

    def test_import_csv(self):
        # Import file
        response = self.import_file(TEST_CSV)

        # Check correct response
        self.assertRedirects(response, self.get_url('show_dictionary'))

        response = self.client.get(self.get_url('show_dictionary'))

        # Check number of imported objects
        self.assertEqual(Dictionary.objects.count(), 164)

    def test_import_csv_header(self):
        # Import file
        response = self.import_file(TEST_CSV_HEADER)

        # Check correct response
        self.assertRedirects(response, self.get_url('show_dictionary'))

        # Check number of imported objects
        self.assertEqual(Dictionary.objects.count(), 164)

    def test_import_po(self):
        # Import file
        response = self.import_file(TEST_PO)

        # Check correct response
        self.assertRedirects(response, self.get_url('show_dictionary'))

        # Check number of imported objects
        self.assertEqual(Dictionary.objects.count(), 164)

    def test_edit(self):
        """Test for manually adding words to glossary."""
        show_url = self.get_url('show_dictionary')

        # Add word
        response = self.client.post(
            show_url,
            {'source': 'source', 'target': 'překlad'}
        )

        # Check correct response
        self.assertRedirects(response, show_url)

        # Check number of objects
        self.assertEqual(Dictionary.objects.count(), 1)

        dict_id = Dictionary.objects.all()[0].id
        edit_url = self.get_url('edit_dictionary', pk=dict_id)

        # Check they are shown
        response = self.client.get(show_url)
        self.assertContains(response, 'překlad')

        # Edit page
        response = self.client.get(edit_url)
        self.assertContains(response, 'překlad')

        # Edit translation
        response = self.client.post(
            edit_url,
            {'source': 'src', 'target': 'přkld'}
        )
        self.assertRedirects(response, show_url)

        # Check they are shown
        response = self.client.get(show_url)
        self.assertContains(response, 'přkld')

        # Test deleting
        delete_url = self.get_url('delete_dictionary', pk=dict_id)
        response = self.client.post(delete_url)
        self.assertRedirects(response, show_url)

        # Check number of objects
        self.assertEqual(Dictionary.objects.count(), 0)

    def test_download_csv(self):
        """Test for downloading CVS file."""
        # Import test data
        self.import_file(TEST_TBX)

        response = self.client.get(
            self.get_url('download_dictionary'),
            {'format': 'csv'}
        )
        self.assertContains(
            response,
            '"addon","doplněk"'
        )

    def test_download_tbx(self):
        """Test for downloading TBX file."""
        # Import test data
        self.import_file(TEST_TBX)

        response = self.client.get(
            self.get_url('download_dictionary'),
            {'format': 'tbx'}
        )
        self.assertContains(
            response,
            '<term>website</term>'
        )
        self.assertContains(
            response,
            '<term>webové stránky</term>'
        )

    def test_download_xliff(self):
        """Test for downloading XLIFF file."""
        # Import test data
        self.import_file(TEST_TBX)

        response = self.client.get(
            self.get_url('download_dictionary'),
            {'format': 'xliff'}
        )
        self.assertContains(
            response,
            '<source>website</source>'
        )
        self.assertContains(
            response,
            '<target state="translated">webové stránky</target>'
        )

    def test_download_po(self):
        """Test for downloading PO file."""
        # Import test data
        self.import_file(TEST_TBX)

        response = self.client.get(
            self.get_url('download_dictionary'),
            {'format': 'po'}
        )
        self.assertContains(
            response,
            'msgid "wizard"\nmsgstr "průvodce"'
        )

    def test_list(self):
        """Test for listing dictionaries."""
        self.import_file(TEST_TBX)

        # List dictionaries
        response = self.client.get(reverse(
            'show_dictionaries',
            kwargs=self.kw_project
        ))
        self.assertContains(response, 'Czech')
        self.assertContains(response, 'Italian')

        dict_url = self.get_url('show_dictionary')

        # List all words
        response = self.client.get(dict_url)
        self.assertContains(response, 'Czech')
        self.assertContains(response, '1 / 4')
        self.assertContains(response, 'datový tok')

        # Filtering by letter
        response = self.client.get(dict_url, {'letter': 'b'})
        self.assertContains(response, 'Czech')
        self.assertContains(response, '1 / 1')
        self.assertContains(response, 'datový tok')

    def test_get_words(self):
        translation = self.get_translation()
        Dictionary.objects.create(
            self.user,
            project=self.project,
            language=translation.language,
            source='hello',
            target='ahoj',
        )
        Dictionary.objects.create(
            self.user,
            project=self.project,
            language=translation.language,
            source='thank',
            target='děkujeme',
        )
        unit = self.get_unit('Thank you for using Weblate.')
        self.assertEqual(
            Dictionary.objects.get_words(unit).count(),
            1
        )
        Dictionary.objects.create(
            self.user,
            project=self.project,
            language=translation.language,
            source='thank',
            target='díky',
        )
        self.assertEqual(
            Dictionary.objects.get_words(unit).count(),
            2
        )
        Dictionary.objects.create(
            self.user,
            project=self.project,
            language=translation.language,
            source='thank you',
            target='děkujeme vám',
        )
        self.assertEqual(
            Dictionary.objects.get_words(unit).count(),
            3
        )
        Dictionary.objects.create(
            self.user,
            project=self.project,
            language=translation.language,
            source='thank you for using Weblate',
            target='děkujeme vám za použití Weblate',
        )
        self.assertEqual(
            Dictionary.objects.get_words(unit).count(),
            4
        )

    def test_get_long(self):
        """Test parsing long source string."""
        unit = self.get_unit()
        unit.source = LONG
        unit.save()
        self.assertEqual(
            Dictionary.objects.get_words(unit).count(),
            0
        )

    def test_get_dash(self):
        translation = self.get_translation()
        unit = self.get_unit('Thank you for using Weblate.')
        unit.source = 'Nordrhein-Westfalen'
        Dictionary.objects.create(
            self.user,
            project=self.project,
            language=translation.language,
            source='Nordrhein-Westfalen',
            target='Northrhine Westfalia'
        )
        self.assertEqual(
            Dictionary.objects.get_words(unit).count(),
            1
        )

    def test_add(self):
        """Test for adding word from translate page"""

        unit = self.get_unit('Thank you for using Weblate.')
        # Add word
        response = self.client.post(
            reverse('js-add-glossary', kwargs={'unit_id': unit.pk}),
            {'source': 'source', 'target': 'překlad'}
        )
        content = json.loads(response.content.decode('utf-8'))
        self.assertEqual(content['responseCode'], 200)
