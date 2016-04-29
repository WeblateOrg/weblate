# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals
import json

from django.test import TestCase
from django.core.cache import cache

import httpretty

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.models.unit import Unit
from weblate.trans.machine.dummy import DummyTranslation
from weblate.trans.machine.glosbe import GlosbeTranslation
from weblate.trans.machine.mymemory import MyMemoryTranslation
from weblate.trans.machine.apertium import ApertiumTranslation
from weblate.trans.machine.tmserver import AmagamaTranslation
from weblate.trans.machine.microsoft import MicrosoftTranslation
from weblate.trans.machine.google import GoogleTranslation
from weblate.trans.machine.weblatetm import (
    WeblateSimilarTranslation, WeblateTranslation
)
from weblate.trans.tests.test_checks import MockUnit

GLOSBE_JSON = '''
{
    "result":"ok",
    "authors":{
        "1":{"U":"http://en.wiktionary.org","id":1,"N":"en.wiktionary.org"}
    },
    "dest":"ces",
    "phrase":"world",
    "tuc":[
        {
            "authors":[1],
            "meaningId":-311020347498476098,
            "meanings":[
                {
                    "text":"geographic terms (above country level)",
                    "language":"eng"
                }
            ],
            "phrase":{"text":"svět","language":"ces"}}],
    "from":"eng"
}
'''.encode('utf-8')
MYMEMORY_JSON = '''
\r\n
{"responseData":{"translatedText":"svět"},"responseDetails":"",
"responseStatus":200,
"matches":[
{"id":"428492143","segment":"world","translation":"svět","quality":"",
"reference":"http://aims.fao.org/standards/agrovoc",
"usage-count":15,"subject":"Agriculture_and_Farming",
"created-by":"MyMemoryLoader",
"last-updated-by":"MyMemoryLoader","create-date":"2013-06-12 17:02:07",
"last-update-date":"2013-06-12 17:02:07","match":1},
{"id":"424273685","segment":"World view","translation":"Světový názor",
"quality":"80",
"reference":"//cs.wikipedia.org/wiki/Sv%C4%9Btov%C3%BD_n%C3%A1zor",
"usage-count":1,"subject":"All","created-by":"","last-updated-by":"Wikipedia",
"create-date":"2012-02-22 13:23:31","last-update-date":"2012-02-22 13:23:31",
"match":0.85},
{"id":"428493395","segment":"World Bank","translation":"IBRD","quality":"",
"reference":"http://aims.fao.org/standards/agrovoc",
"usage-count":1,"subject":"Agriculture_and_Farming",
"created-by":"MyMemoryLoader","last-updated-by":"MyMemoryLoader",
"create-date":"2013-06-12 17:02:07",
"last-update-date":"2013-06-12 17:02:07","match":0.84}
]}
'''.encode('utf-8')
AMAGAMA_JSON = '''
[{"source": "World", "quality": 80.0, "target": "Svět", "rank": 100.0}]
'''.encode('utf-8')


class MachineTranslationTest(TestCase):
    '''
    Testing of machine translation core.
    '''
    def test_support(self):
        machine_translation = DummyTranslation()
        self.assertTrue(machine_translation.is_supported('en', 'cs'))
        self.assertFalse(machine_translation.is_supported('en', 'de'))

    def test_translate(self):
        machine_translation = DummyTranslation()
        self.assertEqual(
            machine_translation.translate('cs', 'Hello', MockUnit(), None),
            []
        )
        self.assertEqual(
            len(
                machine_translation.translate(
                    'cs', 'Hello, world!', MockUnit(), None
                )
            ),
            2
        )

    def assertTranslate(self, machine, lang='cs', word='world', empty=False):
        translation = machine.translate(lang, word, MockUnit(), None)
        self.assertIsInstance(translation, list)
        if not empty:
            self.assertTrue(len(translation) > 0)

    @httpretty.activate
    def test_glosbe(self):
        httpretty.register_uri(
            httpretty.GET,
            'https://glosbe.com/gapi/translate',
            body=GLOSBE_JSON
        )
        machine = GlosbeTranslation()
        self.assertTranslate(machine)

    @httpretty.activate
    def test_mymemory(self):
        httpretty.register_uri(
            httpretty.GET,
            'http://mymemory.translated.net/api/get',
            body=MYMEMORY_JSON
        )
        machine = MyMemoryTranslation()
        self.assertTranslate(machine)

    @httpretty.activate
    def test_apertium(self):
        httpretty.register_uri(
            httpretty.GET,
            'http://api.apertium.org/json/listPairs',
            body='{"responseStatus": 200, "responseData":'
            '[{"sourceLanguage": "en","targetLanguage": "es"}]}'
        )
        httpretty.register_uri(
            httpretty.GET,
            'http://api.apertium.org/json/translate',
            body='{"responseData":{"translatedText":"Mundial"},'
            '"responseDetails":null,"responseStatus":200}'
        )
        machine = ApertiumTranslation()
        self.assertTranslate(machine, 'es')

    @httpretty.activate
    def test_microsoft(self):
        httpretty.register_uri(
            httpretty.POST,
            'https://datamarket.accesscontrol.windows.net/v2/OAuth2-13',
            body='{"access_token":"TOKEN"}'
        )
        httpretty.register_uri(
            httpretty.GET,
            'http://api.microsofttranslator.com/V2/Ajax.svc/'
            'GetLanguagesForTranslate',
            body='["en","cs"]'
        )
        httpretty.register_uri(
            httpretty.GET,
            'http://api.microsofttranslator.com/V2/Ajax.svc/Translate',
            body='"svět"'.encode('utf-8')
        )

        machine = MicrosoftTranslation()
        self.assertTranslate(machine)

    @httpretty.activate
    def test_google(self):
        cache.delete('%s-languages' % GoogleTranslation().mtid)
        httpretty.register_uri(
            httpretty.GET,
            'https://www.googleapis.com/language/translate/v2/languages',
            body=json.dumps(
                {
                    'data': {
                        'languages': [
                            {'language': 'en'},
                            {'language': 'iw'},
                            {'language': 'cs'}
                        ]
                    }
                }
            )
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://www.googleapis.com/language/translate/v2/',
            body=b'{"data":{"translations":[{"translatedText":"svet"}]}}'
        )
        machine = GoogleTranslation()
        self.assertTranslate(machine)
        self.assertTranslate(machine, lang='he')

    @httpretty.activate
    def test_google_invalid(self):
        """Test handling of server failure."""
        cache.delete('%s-languages' % GoogleTranslation().mtid)
        httpretty.register_uri(
            httpretty.GET,
            'https://www.googleapis.com/language/translate/v2/languages',
            body='',
            status=500,
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://www.googleapis.com/language/translate/v2/',
            body='',
            status=500,
        )
        machine = GoogleTranslation()
        self.assertEqual(machine.supported_languages, [])
        self.assertTranslate(machine, empty=True)

    @httpretty.activate
    def test_amagama(self):
        httpretty.register_uri(
            httpretty.GET,
            'http://amagama.locamotion.org/tmserver/en/cs/unit/world',
            body=AMAGAMA_JSON
        )
        machine = AmagamaTranslation()
        self.assertTranslate(machine)


class WeblateTranslationTest(ViewTestCase):
    def test_same(self):
        machine = WeblateTranslation()
        unit = Unit.objects.all()[0]
        results = machine.translate(
            unit.translation.language.code,
            unit.get_source_plurals()[0],
            unit,
            self.user
        )
        self.assertEqual(results, [])

    def test_similar(self):
        machine = WeblateSimilarTranslation()
        unit = Unit.objects.all()[0]
        results = machine.translate(
            unit.translation.language.code,
            unit.get_source_plurals()[0],
            unit,
            self.user
        )
        self.assertEqual(results, [])
