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

from __future__ import unicode_literals
import json

from botocore.stub import Stubber, ANY

from django.test import TestCase
from django.test.utils import override_settings

import httpretty

from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.trans.models.unit import Unit
from weblate.machinery.base import MachineTranslationError
from weblate.machinery.baidu import BaiduTranslation, BAIDU_API
from weblate.machinery.dummy import DummyTranslation
from weblate.machinery.deepl import DeepLTranslation
from weblate.machinery.glosbe import GlosbeTranslation
from weblate.machinery.mymemory import MyMemoryTranslation
from weblate.machinery.apertium import ApertiumAPYTranslation
from weblate.machinery.aws import AWSTranslation
from weblate.machinery.tmserver import AmagamaTranslation, AMAGAMA_LIVE
from weblate.machinery.microsoft import (
    MicrosoftTranslation, MicrosoftCognitiveTranslation,
)
from weblate.machinery.microsoftterminology import MicrosoftTerminologyService
from weblate.machinery.google import GoogleTranslation, GOOGLE_API_ROOT
from weblate.machinery.yandex import YandexTranslation
from weblate.machinery.youdao import YoudaoTranslation
from weblate.machinery.saptranslationhub import SAPTranslationHub
from weblate.machinery.weblatetm import WeblateTranslation
from weblate.checks.tests.test_checks import MockUnit

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
SAPTRANSLATIONHUB_JSON = '''
{
    "units": [
        {
            "textType": "XFLD",
            "domain": "BC",
            "key": "LOGIN_USERNAME_FIELD",
            "value": "User Name",
            "translations": [
                {
                    "language": "es",
                    "value": "Usuario",
                    "translationProvider": 0,
                    "qualityIndex": 100
                }
            ]
        }
    ]
}
'''.encode('utf-8')

TERMINOLOGY_LANGUAGES = '''
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <GetLanguagesResponse xmlns="http://api.terminology.microsoft.com/terminology">
      <GetLanguagesResult xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
        <Language>
          <Code>af-za</Code>
        </Language>
        <Language>
          <Code>am-et</Code>
        </Language>
        <Language>
          <Code>ar-dz</Code>
        </Language>
        <Language>
          <Code>ar-eg</Code>
        </Language>
        <Language>
          <Code>ar-sa</Code>
        </Language>
        <Language>
          <Code>as-in</Code>
        </Language>
        <Language>
          <Code>az-latn-az</Code>
        </Language>
        <Language>
          <Code>be-by</Code>
        </Language>
        <Language>
          <Code>bg-bg</Code>
        </Language>
        <Language>
          <Code>bn-bd</Code>
        </Language>
        <Language>
          <Code>bn-in</Code>
        </Language>
        <Language>
          <Code>bs-cyrl-ba</Code>
        </Language>
        <Language>
          <Code>bs-latn-ba</Code>
        </Language>
        <Language>
          <Code>ca-es</Code>
        </Language>
        <Language>
          <Code>ca-es-valencia</Code>
        </Language>
        <Language>
          <Code>chr-cher-us</Code>
        </Language>
        <Language>
          <Code>cs-cz</Code>
        </Language>
        <Language>
          <Code>en-us</Code>
        </Language>
      </GetLanguagesResult>
    </GetLanguagesResponse>
  </s:Body>
</s:Envelope>
'''.encode('utf-8')
TERMINOLOGY_TRANSLATE = '''
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <GetTranslationsResponse xmlns="http://api.terminology.microsoft.com/terminology">
      <GetTranslationsResult xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
        <Match>
          <ConfidenceLevel>100</ConfidenceLevel>
          <Count>8</Count>
          <Definition i:nil="true"/>
          <OriginalText>Hello World</OriginalText>
          <Product i:nil="true"/>
          <ProductVersion i:nil="true"/>
          <Source i:nil="true"/>
          <Translations>
            <Translation>
              <Language>cs-cz</Language>
              <TranslatedText>Hello World</TranslatedText>
            </Translation>
          </Translations>
        </Match>
        <Match>
          <ConfidenceLevel>100</ConfidenceLevel>
          <Count>1</Count>
          <Definition i:nil="true"/>
          <OriginalText>Hello world.</OriginalText>
          <Product i:nil="true"/>
          <ProductVersion i:nil="true"/>
          <Source i:nil="true"/>
          <Translations>
            <Translation>
              <Language>cs-cz</Language>
              <TranslatedText>Ahoj sv&#x11B;te.</TranslatedText>
            </Translation>
          </Translations>
        </Match>
      </GetTranslationsResult>
    </GetTranslationsResponse>
  </s:Body>
</s:Envelope>
'''.encode('utf-8')
TERMINOLOGY_WDSL = get_test_file('microsoftterminology.wsdl')

DEEPL_RESPONSE = b'''{
    "translations": [
        { "detected_source_language": "EN", "text": "Hallo" }
    ]
}'''


class MachineTranslationTest(TestCase):
    """Testing of machine translation core."""
    def get_machine(self, cls):
        machine = cls()
        machine.delete_cache()
        machine.cache_translations = False
        return machine

    def test_support(self):
        machine_translation = self.get_machine(DummyTranslation)
        self.assertTrue(machine_translation.is_supported('en', 'cs'))
        self.assertFalse(machine_translation.is_supported('en', 'de'))

    def test_translate(self):
        machine_translation = self.get_machine(DummyTranslation)
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

    def test_translate_fallback(self):
        machine_translation = self.get_machine(DummyTranslation)
        self.assertEqual(
            len(
                machine_translation.translate(
                    'cs_CZ', 'Hello, world!', MockUnit(), None
                )
            ),
            2
        )

    def test_translate_fallback_missing(self):
        machine_translation = self.get_machine(DummyTranslation)
        self.assertEqual(
            machine_translation.translate(
                'de_CZ', 'Hello, world!', MockUnit(), None
            ),
            []
        )

    def assert_translate(self, machine, lang='cs', word='world', empty=False):
        translation = machine.translate(lang, word, MockUnit(), None)
        self.assertIsInstance(translation, list)
        if not empty:
            self.assertTrue(translation)

    @httpretty.activate
    def test_glosbe(self):
        machine = self.get_machine(GlosbeTranslation)
        httpretty.register_uri(
            httpretty.GET,
            'https://glosbe.com/gapi/translate',
            body=GLOSBE_JSON
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word='Zkouška')

    @httpretty.activate
    def test_glosbe_ratelimit(self):
        machine = self.get_machine(GlosbeTranslation)
        httpretty.register_uri(
            httpretty.GET,
            'https://glosbe.com/gapi/translate',
            body=GLOSBE_JSON,
            status=429,
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, empty=True)
        self.assert_translate(machine, empty=True)

    @httpretty.activate
    def test_glosbe_ratelimit_set(self):
        machine = self.get_machine(GlosbeTranslation)
        machine.set_rate_limit()
        httpretty.register_uri(
            httpretty.GET,
            'https://glosbe.com/gapi/translate',
            body=GLOSBE_JSON
        )
        self.assert_translate(machine, empty=True)

    @override_settings(MT_MYMEMORY_EMAIL='test@weblate.org')
    @httpretty.activate
    def test_mymemory(self):
        machine = self.get_machine(MyMemoryTranslation)
        httpretty.register_uri(
            httpretty.GET,
            'https://mymemory.translated.net/api/get',
            body=MYMEMORY_JSON
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word='Zkouška')

    @override_settings(MT_APERTIUM_APY='http://apertium.example.com/')
    @httpretty.activate
    def test_apertium_apy(self):
        machine = self.get_machine(ApertiumAPYTranslation)
        httpretty.register_uri(
            httpretty.GET,
            'http://apertium.example.com/listPairs',
            body='{"responseStatus": 200, "responseData":'
            '[{"sourceLanguage": "eng","targetLanguage": "spa"}]}'
        )
        httpretty.register_uri(
            httpretty.GET,
            'http://apertium.example.com/translate',
            body='{"responseData":{"translatedText":"Mundial"},'
            '"responseDetails":null,"responseStatus":200}'
        )
        self.assert_translate(machine, 'es')
        self.assert_translate(machine, 'es', word='Zkouška')

    @override_settings(MT_MICROSOFT_ID='ID', MT_MICROSOFT_SECRET='SECRET')
    @httpretty.activate
    def test_microsoft(self):
        machine = self.get_machine(MicrosoftTranslation)
        httpretty.register_uri(
            httpretty.POST,
            'https://datamarket.accesscontrol.windows.net/v2/OAuth2-13',
            body='{"access_token":"TOKEN"}'
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://api.microsofttranslator.com/V2/Ajax.svc/'
            'GetLanguagesForTranslate',
            body='["en","cs"]'
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://api.microsofttranslator.com/V2/Ajax.svc/Translate',
            body='"svět"'.encode('utf-8')
        )

        self.assert_translate(machine)
        self.assert_translate(machine, word='Zkouška')

    @override_settings(MT_MICROSOFT_COGNITIVE_KEY='KEY')
    @httpretty.activate
    def test_microsoft_cognitive(self):
        machine = self.get_machine(MicrosoftCognitiveTranslation)
        httpretty.register_uri(
            httpretty.POST,
            'https://api.cognitive.microsoft.com/sts/v1.0/issueToken'
            '?Subscription-Key=KEY',
            body='TOKEN'
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://api.microsofttranslator.com/V2/Ajax.svc/'
            'GetLanguagesForTranslate',
            body='["en","cs"]'
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://api.microsofttranslator.com/V2/Ajax.svc/Translate',
            body='"svět"'.encode('utf-8')
        )

        self.assert_translate(machine)
        self.assert_translate(machine, word='Zkouška')

    def register_microsoft_terminology(self):
        with open(TERMINOLOGY_WDSL, 'rb') as handle:
            httpretty.register_uri(
                httpretty.GET,
                'http://api.terminology.microsoft.com/Terminology.svc',
                body=handle.read(),
                content_type='text/xml',
            )

    @httpretty.activate
    def test_microsoft_terminology(self):
        def request_callback(request, uri, headers):
            if b'GetLanguages' in request.body:
                return (200, headers, TERMINOLOGY_LANGUAGES)
            return (200, headers, TERMINOLOGY_TRANSLATE)

        self.register_microsoft_terminology()

        machine = self.get_machine(MicrosoftTerminologyService)
        httpretty.register_uri(
            httpretty.POST,
            'http://api.terminology.microsoft.com/Terminology.svc',
            body=request_callback,
            content_type='text/xml',
        )
        self.assert_translate(machine)
        self.assert_translate(machine, lang='cs_CZ')

    @httpretty.activate
    def test_microsoft_terminology_error(self):
        self.register_microsoft_terminology()
        machine = self.get_machine(MicrosoftTerminologyService)
        httpretty.register_uri(
            httpretty.POST,
            'http://api.terminology.microsoft.com/Terminology.svc',
            body='',
            content_type='text/xml',
            status=500,
        )
        self.assertEqual(machine.supported_languages, [])
        self.assert_translate(machine, empty=True)

    @override_settings(MT_GOOGLE_KEY='KEY')
    @httpretty.activate
    def test_google(self):
        machine = self.get_machine(GoogleTranslation)
        httpretty.register_uri(
            httpretty.GET,
            GOOGLE_API_ROOT + 'languages',
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
            GOOGLE_API_ROOT,
            body=b'{"data":{"translations":[{"translatedText":"svet"}]}}'
        )
        self.assert_translate(machine)
        self.assert_translate(machine, lang='he')
        self.assert_translate(machine, word='Zkouška')

    @override_settings(MT_GOOGLE_KEY='KEY')
    @httpretty.activate
    def test_google_invalid(self):
        """Test handling of server failure."""
        machine = self.get_machine(GoogleTranslation)
        httpretty.register_uri(
            httpretty.GET,
            GOOGLE_API_ROOT + 'languages',
            body='',
            status=500,
        )
        httpretty.register_uri(
            httpretty.GET,
            GOOGLE_API_ROOT,
            body='',
            status=500,
        )
        self.assertEqual(machine.supported_languages, [])
        self.assert_translate(machine, empty=True)

    @httpretty.activate
    def test_amagama_nolang(self):
        machine = self.get_machine(AmagamaTranslation)
        httpretty.register_uri(
            httpretty.GET,
            AMAGAMA_LIVE + '/languages/',
            body='',
            status=404,
        )
        httpretty.register_uri(
            httpretty.GET,
            AMAGAMA_LIVE + '/en/cs/unit/world',
            body=AMAGAMA_JSON
        )
        httpretty.register_uri(
            httpretty.GET,
            AMAGAMA_LIVE + '/en/cs/unit/Zkou%C5%A1ka',
            body=AMAGAMA_JSON
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word='Zkouška')

    @override_settings(DEBUG=True)
    def test_amagama_nolang_debug(self):
        self.test_amagama_nolang()

    @httpretty.activate
    def test_amagama(self):
        machine = self.get_machine(AmagamaTranslation)
        httpretty.register_uri(
            httpretty.GET,
            AMAGAMA_LIVE + '/languages/',
            body='{"sourceLanguages": ["en"], "targetLanguages": ["cs"]}',
        )
        httpretty.register_uri(
            httpretty.GET,
            AMAGAMA_LIVE + '/en/cs/unit/world',
            body=AMAGAMA_JSON
        )
        httpretty.register_uri(
            httpretty.GET,
            AMAGAMA_LIVE + '/en/cs/unit/Zkou%C5%A1ka',
            body=AMAGAMA_JSON
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word='Zkouška')

    @override_settings(MT_YANDEX_KEY='KEY')
    @httpretty.activate
    def test_yandex(self):
        machine = self.get_machine(YandexTranslation)
        httpretty.register_uri(
            httpretty.GET,
            'https://translate.yandex.net/api/v1.5/tr.json/getLangs',
            body=b'{"dirs": ["en-cs"]}'
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://translate.yandex.net/api/v1.5/tr.json/translate',
            body=b'{"code": 200, "lang": "en-cs", "text": ["svet"]}'
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word='Zkouška')

    @override_settings(MT_YANDEX_KEY='KEY')
    @httpretty.activate
    def test_yandex_error(self):
        machine = self.get_machine(YandexTranslation)
        httpretty.register_uri(
            httpretty.GET,
            'https://translate.yandex.net/api/v1.5/tr.json/getLangs',
            body=b'{"code": 401}'
        )
        httpretty.register_uri(
            httpretty.GET,
            'https://translate.yandex.net/api/v1.5/tr.json/translate',
            body=b'{"code": 401, "message": "Invalid request"}'
        )
        self.assertEqual(machine.supported_languages, [])
        self.assert_translate(machine, empty=True)

    @override_settings(MT_YOUDAO_ID='id', MT_YOUDAO_SECRET='secret')
    @httpretty.activate
    def test_youdao(self):
        machine = self.get_machine(YoudaoTranslation)
        httpretty.register_uri(
            httpretty.GET,
            'https://openapi.youdao.com/api',
            body=b'{"errorCode": 0, "translation": ["hello"]}',
        )
        self.assert_translate(machine, lang='ja')
        self.assert_translate(machine, lang='ja', word='Zkouška')

    @override_settings(MT_YOUDAO_ID='id', MT_YOUDAO_SECRET='secret')
    @httpretty.activate
    def test_youdao_error(self):
        machine = self.get_machine(YoudaoTranslation)
        httpretty.register_uri(
            httpretty.GET,
            'https://openapi.youdao.com/api',
            body=b'{"errorCode": 1}',
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, lang='ja', empty=True)

    @override_settings(MT_BAIDU_ID='id', MT_BAIDU_SECRET='secret')
    @httpretty.activate
    def test_baidu(self):
        machine = self.get_machine(BaiduTranslation)
        httpretty.register_uri(
            httpretty.GET,
            BAIDU_API,
            body=b'{"trans_result": [{"src": "hello", "dst": "hallo"}]}',
        )
        self.assert_translate(machine, lang='ja')
        self.assert_translate(machine, lang='ja', word='Zkouška')

    @override_settings(MT_BAIDU_ID='id', MT_BAIDU_SECRET='secret')
    @httpretty.activate
    def test_baidu_error(self):
        machine = self.get_machine(BaiduTranslation)
        httpretty.register_uri(
            httpretty.GET,
            BAIDU_API,
            body=b'{"error_code": 1, "error_msg": "Error"}',
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, lang='ja', empty=True)

    @override_settings(MT_SAP_BASE_URL='http://sth.example.com/')
    @override_settings(MT_SAP_SANDBOX_APIKEY='http://sandbox.example.com')
    @override_settings(MT_SAP_USERNAME='username')
    @override_settings(MT_SAP_PASSWORD='password')
    @httpretty.activate
    def test_saptranslationhub(self):
        machine = self.get_machine(SAPTranslationHub)
        httpretty.register_uri(
            httpretty.GET,
            'http://sth.example.com/languages',
            body=json.dumps(
                {
                    'languages': [
                        {
                            'id': 'en',
                            'name': 'English',
                            'bcp-47-code': 'en'
                        },
                        {
                            'id': 'cs',
                            'name': 'Czech',
                            'bcp-47-code': 'cs'
                        }
                    ]
                }
            ),
            status=200,
        )
        httpretty.register_uri(
            httpretty.POST,
            'http://sth.example.com/translate',
            body=SAPTRANSLATIONHUB_JSON,
            status=200,
            content_type='text/json'
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word='Zkouška')

    @override_settings(MT_SAP_BASE_URL='http://sth.example.com/')
    @httpretty.activate
    def test_saptranslationhub_invalid(self):
        machine = self.get_machine(SAPTranslationHub)
        httpretty.register_uri(
            httpretty.GET,
            'http://sth.example.com/languages',
            body='',
            status=500
        )
        httpretty.register_uri(
            httpretty.POST,
            'http://sth.example.com/translate',
            body='',
            status=500
        )
        self.assertEqual(machine.supported_languages, [])
        self.assert_translate(machine, empty=True)

    @override_settings(MT_DEEPL_KEY='KEY')
    @httpretty.activate
    def test_deepl(self):
        machine = self.get_machine(DeepLTranslation)
        httpretty.register_uri(
            httpretty.POST,
            'https://api.deepl.com/v1/translate',
            body=DEEPL_RESPONSE,
        )
        self.assert_translate(machine, lang='de', word='Hello')

    @override_settings(MT_DEEPL_KEY='KEY')
    @httpretty.activate
    def test_cache(self):
        machine = self.get_machine(DeepLTranslation)
        machine.cache_translations = True
        httpretty.register_uri(
            httpretty.POST,
            'https://api.deepl.com/v1/translate',
            body=DEEPL_RESPONSE,
        )
        # Fetch from service
        self.assert_translate(machine, lang='de', word='Hello')
        self.assertTrue(httpretty.has_request())
        httpretty.reset()
        # Fetch from cache
        self.assert_translate(machine, lang='de', word='Hello')
        self.assertFalse(httpretty.has_request())

    @override_settings(MT_AWS_REGION='us-west-2')
    def test_aws(self):
        machine = self.get_machine(AWSTranslation)
        with Stubber(machine.client) as stubber:
            stubber.add_response(
                'translate_text',
                {
                    'TranslatedText': 'Hallo',
                    'SourceLanguageCode': 'en',
                    'TargetLanguageCode': 'de',
                },
                {
                    'SourceLanguageCode': ANY,
                    'TargetLanguageCode': ANY,
                    'Text': ANY,
                }
            )
            self.assert_translate(machine, lang='de', word='Hello')


class WeblateTranslationTest(FixtureTestCase):
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
