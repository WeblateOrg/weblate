# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

import httpretty
from django.test import TestCase
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.models.unit import Unit
from weblate.trans.machine.dummy import DummyTranslation
from weblate.trans.machine.glosbe import GlosbeTranslation
from weblate.trans.machine.mymemory import MyMemoryTranslation
from weblate.trans.machine.apertium import ApertiumTranslation
from weblate.trans.machine.tmserver import AmagamaTranslation
from weblate.trans.machine.microsoft import MicrosoftTranslation
from weblate.trans.machine.google import (
    GoogleWebTranslation, GoogleTranslation
)
from weblate.trans.machine.weblatetm import (
    WeblateSimilarTranslation, WeblateTranslation
)

GLOSBE_JSON = u'''
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
MYMEMORY_JSON = u'''
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
AMAGAMA_JSON = u'''
[{"source": "World", "quality": 80.0, "target": "Svět", "rank": 100.0}]
'''.encode('utf-8')
GOOGLE_JSON = u'''
[
    [["svět","world","",""]],
    [[
        "noun",["svět","země","společnost","lidstvo"],
        [
            ["svět",["world","earth"],null,0.465043187],
            ["země",["country","land","ground","nation","soil","world"]
            ,null,0.000656803953],
            ["lidstvo",["humanity","mankind","humankind","people","world"]
            ,null,0.000148860636]
        ],
        "world",1
    ]],
    "en",null,
    [["svět",[4],1,0,1000,0,1,0]],
    [[
        "world",4,[["svět",1000,1,0],
        ["World",0,1,0],
        ["Světová",0,1,0],
        ["světě",0,1,0],
        ["světa",0,1,0]],
        [[0,5]],"world"]],
    null,null,[],2
]
'''.encode('utf-8')


class MachineTranslationTest(TestCase):
    '''
    Testing of machine translation core.
    '''
    def test_support(self):
        machine_translation = DummyTranslation()
        self.assertTrue(machine_translation.is_supported('cs'))
        self.assertFalse(machine_translation.is_supported('de'))

    def test_translate(self):
        machine_translation = DummyTranslation()
        self.assertEqual(
            machine_translation.translate('cs', 'Hello', None, None),
            []
        )
        self.assertEqual(
            len(
                machine_translation.translate(
                    'cs', 'Hello, world!', None, None
                )
            ),
            2
        )

    def assertTranslate(self, machine, lang='cs', word='world', empty=False):
        translation = machine.translate(lang, word, None, None)
        self.assertIsInstance(translation, list)
        if not empty:
            self.assertTrue(len(translation) > 0)

    @httpretty.activate
    def test_glosbe(self):
        httpretty.register_uri(
            httpretty.GET,
            'http://glosbe.com/gapi/translate',
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
            body=u'"svět"'.encode('utf-8')
        )

        machine = MicrosoftTranslation()
        self.assertTranslate(machine)

    @httpretty.activate
    def test_googleweb(self):
        httpretty.register_uri(
            httpretty.GET,
            'http://translate.google.com/translate_a/t',
            body=GOOGLE_JSON
        )
        machine = GoogleWebTranslation()
        self.assertTranslate(machine)

    @httpretty.activate
    def test_google(self):
        httpretty.register_uri(
            httpretty.GET,
            'https://www.googleapis.com/language/translate/v2/languages',
            body='{"data": {"languages": [ { "language": "cs" }]}}'
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://www.googleapis.com/language/translate/v2/',
            body='{"data":{"translations":[{"translatedText":"svet"}]}}'
        )
        machine = GoogleTranslation()
        self.assertTranslate(machine)

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
