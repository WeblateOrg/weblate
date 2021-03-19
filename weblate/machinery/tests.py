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

from copy import copy
from typing import Type
from unittest import SkipTest
from unittest.mock import Mock, patch

import responses
from botocore.stub import ANY, Stubber
from django.test import TestCase
from django.test.utils import override_settings
from google.cloud.translate_v3 import (
    SupportedLanguages,
    TranslateTextResponse,
    TranslationServiceClient,
)

from weblate.checks.tests.test_checks import MockUnit
from weblate.machinery.apertium import ApertiumAPYTranslation
from weblate.machinery.aws import AWSTranslation
from weblate.machinery.baidu import BAIDU_API, BaiduTranslation
from weblate.machinery.base import (
    MachineryRateLimit,
    MachineTranslation,
    MachineTranslationError,
    MissingConfiguration,
)
from weblate.machinery.deepl import DEEPL_LANGUAGES, DEEPL_TRANSLATE, DeepLTranslation
from weblate.machinery.dummy import DummyTranslation
from weblate.machinery.glosbe import GlosbeTranslation
from weblate.machinery.google import GOOGLE_API_ROOT, GoogleTranslation
from weblate.machinery.googlev3 import GoogleV3Translation
from weblate.machinery.microsoft import MicrosoftCognitiveTranslation
from weblate.machinery.microsoftterminology import (
    MST_API_URL,
    MicrosoftTerminologyService,
)
from weblate.machinery.modernmt import ModernMTTranslation
from weblate.machinery.mymemory import MyMemoryTranslation
from weblate.machinery.netease import NETEASE_API_ROOT, NeteaseSightTranslation
from weblate.machinery.saptranslationhub import SAPTranslationHub
from weblate.machinery.tmserver import AMAGAMA_LIVE, AmagamaTranslation
from weblate.machinery.weblatetm import WeblateTranslation
from weblate.machinery.yandex import YandexTranslation
from weblate.machinery.youdao import YoudaoTranslation
from weblate.trans.models.unit import Unit
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.db import using_postgresql
from weblate.utils.state import STATE_TRANSLATED

GLOSBE_JSON = {
    "result": "ok",
    "authors": {
        "1": {"U": "http://en.wiktionary.org", "id": 1, "N": "en.wiktionary.org"}
    },
    "dest": "ces",
    "phrase": "world",
    "tuc": [
        {
            "authors": [1],
            "meaningId": -311020347498476098,
            "meanings": [
                {"text": "geographic terms (above country level)", "language": "eng"}
            ],
            "phrase": {"text": "svět", "language": "ces"},
        }
    ],
    "from": "eng",
}
MYMEMORY_JSON = {
    "responseData": {"translatedText": "svět"},
    "responseDetails": "",
    "responseStatus": 200,
    "matches": [
        {
            "id": "428492143",
            "segment": "world",
            "translation": "svět",
            "quality": "",
            "reference": "http://aims.fao.org/standards/agrovoc",
            "usage-count": 15,
            "subject": "Agriculture_and_Farming",
            "created-by": "MyMemoryLoader",
            "last-updated-by": "MyMemoryLoader",
            "create-date": "2013-06-12 17:02:07",
            "last-update-date": "2013-06-12 17:02:07",
            "match": 1,
        },
        {
            "id": "424273685",
            "segment": "World view",
            "translation": "Světový názor",
            "quality": "80",
            "reference": "//cs.wikipedia.org/wiki/Sv%C4%9Btov%C3%BD_n%C3%A1zor",
            "usage-count": 1,
            "subject": "All",
            "created-by": "",
            "last-updated-by": "Wikipedia",
            "create-date": "2012-02-22 13:23:31",
            "last-update-date": "2012-02-22 13:23:31",
            "match": 0.85,
        },
        {
            "id": "428493395",
            "segment": "World Bank",
            "translation": "IBRD",
            "quality": "",
            "reference": "http://aims.fao.org/standards/agrovoc",
            "usage-count": 1,
            "subject": "Agriculture_and_Farming",
            "created-by": "MyMemoryLoader",
            "last-updated-by": "MyMemoryLoader",
            "create-date": "2013-06-12 17:02:07",
            "last-update-date": "2013-06-12 17:02:07",
            "match": 0.84,
        },
    ],
}
AMAGAMA_JSON = [{"source": "World", "quality": 80.0, "target": "Svět", "rank": 100.0}]
SAPTRANSLATIONHUB_JSON = {
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
                    "qualityIndex": 100,
                }
            ],
        }
    ]
}

TERMINOLOGY_LANGUAGES = b"""
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
"""
TERMINOLOGY_TRANSLATE = b"""
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
"""
TERMINOLOGY_WDSL = get_test_file("microsoftterminology.wsdl")

GOOGLEV3_KEY = get_test_file("googlev3.json")

DEEPL_RESPONSE = {"translations": [{"detected_source_language": "EN", "text": "Hallo"}]}
DEEPL_LANG_RESPONSE = [
    {"language": "EN", "name": "English"},
    {"language": "DE", "name": "Deutsch"},
]
MICROSOFT_RESPONSE = [{"translations": [{"text": "Svět.", "to": "cs"}]}]

MS_SUPPORTED_LANG_RESP = {"translation": {"cs": "data", "en": "data", "es": "data"}}


class BaseMachineTranslationTest(TestCase):
    """Testing of machine translation core."""

    MACHINE_CLS: Type[MachineTranslation] = DummyTranslation
    ENGLISH = "en"
    SUPPORTED = "cs"
    SUPPORTED_VARIANT = "cs_CZ"
    NOTSUPPORTED = "de"
    NOTSUPPORTED_VARIANT = "de_CZ"
    SOURCE_BLANK = "Hello"
    SOURCE_TRANSLATED = "Hello, world!"
    EXPECTED_LEN = 2

    def get_machine(self, cache=False):
        machine = self.MACHINE_CLS()
        machine.delete_cache()
        machine.cache_translations = cache
        return machine

    def test_english_map(self):
        machine = self.get_machine()
        self.assertEqual(machine.map_language_code("en_devel"), self.ENGLISH)

    @responses.activate
    def test_support(self):
        self.mock_response()
        machine_translation = self.get_machine()
        self.assertTrue(machine_translation.is_supported(self.ENGLISH, self.SUPPORTED))
        if self.NOTSUPPORTED:
            self.assertFalse(
                machine_translation.is_supported(self.ENGLISH, self.NOTSUPPORTED)
            )

    def assert_translate(self, lang, word, expected_len, machine=None, cache=False):
        if machine is None:
            machine = self.get_machine(cache=cache)
        translation = machine.translate(MockUnit(code=lang, source=word))
        self.assertIsInstance(translation, list)
        self.assertEqual(len(translation), expected_len)
        for result in translation:
            for key, value in result.items():
                if key == "quality":
                    self.assertIsInstance(
                        value, int, f"'{key}' is supposed to be a integer"
                    )
                else:
                    self.assertIsInstance(
                        value, str, f"'{key}' is supposed to be a string"
                    )

    def mock_empty(self):
        pass

    def mock_response(self):
        pass

    def mock_error(self):
        raise SkipTest("Not tested")

    @responses.activate
    def test_translate_empty(self):
        self.mock_empty()
        self.assert_translate(self.SUPPORTED, self.SOURCE_BLANK, 0)

    @responses.activate
    def test_translate(self, **kwargs):
        self.mock_response()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, **kwargs
        )

    @responses.activate
    def test_batch(self, machine=None):
        self.mock_response()
        if machine is None:
            machine = self.get_machine()
        unit = MockUnit(code=self.SUPPORTED, source=self.SOURCE_TRANSLATED)
        machine.batch_translate([unit])
        self.assertNotEqual(unit.machinery["best"], -1)
        self.assertIn("translation", unit.machinery)

    @responses.activate
    def test_error(self):
        self.mock_error()
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(self.SUPPORTED, self.SOURCE_BLANK, 0)


class MachineTranslationTest(BaseMachineTranslationTest):
    def test_translate_fallback(self):
        machine_translation = self.get_machine()
        self.assertEqual(
            len(
                machine_translation.translate(
                    MockUnit(code=self.SUPPORTED_VARIANT, source=self.SOURCE_TRANSLATED)
                ),
            ),
            self.EXPECTED_LEN,
        )

    def test_translate_fallback_missing(self):
        machine_translation = self.get_machine()
        self.assertEqual(
            machine_translation.translate(
                MockUnit(code=self.NOTSUPPORTED_VARIANT, source=self.SOURCE_TRANSLATED)
            ),
            [],
        )

    def test_placeholders(self):
        machine_translation = self.get_machine()
        unit = MockUnit(code="cs", source="Hello, %s!", flags="c-format")
        self.assertEqual(
            machine_translation.cleanup_text(unit), ("Hello, [7]!", {"[7]": "%s"})
        )
        self.assertEqual(
            machine_translation.translate(unit),
            [
                {
                    "quality": 100,
                    "service": "Dummy",
                    "source": "Hello, %s!",
                    "text": "Nazdar %s!",
                }
            ],
        )


class GlosbeTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = GlosbeTranslation
    EXPECTED_LEN = 1
    NOTSUPPORTED = None

    def mock_empty(self):
        response = copy(GLOSBE_JSON)
        response["tuc"] = []
        responses.add(responses.GET, "https://glosbe.com/gapi/translate", json=response)

    def mock_response(self):
        responses.add(
            responses.GET, "https://glosbe.com/gapi/translate", json=GLOSBE_JSON
        )

    def mock_error(self):
        responses.add(
            responses.GET,
            "https://glosbe.com/gapi/translate",
            json=GLOSBE_JSON,
            status=429,
        )

    def test_ratelimit(self):
        """Test rate limit response handling."""
        # This raises an exception
        self.test_error()
        # The second call should not perform due to rate limiting being cached
        machine = self.MACHINE_CLS()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, 0, machine=machine
        )

    @responses.activate
    def test_ratelimit_set(self):
        """Test manual setting of rate limit."""
        machine = self.MACHINE_CLS()
        machine.delete_cache()
        machine.set_rate_limit()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, 0, machine=machine
        )


@override_settings(MT_MYMEMORY_EMAIL="test@weblate.org")
class MyMemoryTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = MyMemoryTranslation
    EXPECTED_LEN = 3
    NOTSUPPORTED = "ia"

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        raise SkipTest("Not tested")

    def mock_response(self):
        responses.add(
            responses.GET, "https://mymemory.translated.net/api/get", json=MYMEMORY_JSON
        )


@override_settings(MT_APERTIUM_APY="http://apertium.example.com/")
class ApertiumAPYTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = ApertiumAPYTranslation
    ENGLISH = "eng"
    SUPPORTED = "spa"
    EXPECTED_LEN = 1

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        raise SkipTest("Not tested")

    def mock_response(self):
        responses.add(
            responses.GET,
            "http://apertium.example.com/listPairs",
            json={
                "responseStatus": 200,
                "responseData": [{"sourceLanguage": "eng", "targetLanguage": "spa"}],
            },
        )
        responses.add(
            responses.GET,
            "http://apertium.example.com/translate",
            json={
                "responseData": {"translatedText": "Mundial"},
                "responseDetails": None,
                "responseStatus": 200,
            },
        )

    @responses.activate
    def test_translations_cache(self):
        self.mock_response()
        machine = self.MACHINE_CLS()
        machine.delete_cache()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 2)
        responses.reset()
        # New instance should use cached languages and translations
        machine = self.MACHINE_CLS()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 0)


@override_settings(MT_MICROSOFT_COGNITIVE_KEY="KEY")
class MicrosoftCognitiveTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = MicrosoftCognitiveTranslation
    EXPECTED_LEN = 1

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        raise SkipTest("Not tested")

    def mock_response(self):
        responses.add(
            responses.POST,
            "https://api.cognitive.microsoft.com/sts/v1.0/issueToken"
            "?Subscription-Key=KEY",
            body="TOKEN",
        )
        responses.add(
            responses.GET,
            "https://api.cognitive.microsofttranslator.com/"
            "languages?api-version=3.0",
            json=MS_SUPPORTED_LANG_RESP,
        )
        responses.add(
            responses.POST,
            "https://api.cognitive.microsofttranslator.com/"
            "translate?api-version=3.0&from=en&to=cs&category=general",
            json=MICROSOFT_RESPONSE,
        )


@override_settings(MT_MICROSOFT_COGNITIVE_KEY="KEY", MT_MICROSOFT_REGION="westeurope")
class MicrosoftCognitiveTranslationRegionTest(MicrosoftCognitiveTranslationTest):
    def mock_response(self):
        responses.add(
            responses.POST,
            "https://westeurope.api.cognitive.microsoft.com/sts/v1.0/issueToken"
            "?Subscription-Key=KEY",
            body="TOKEN",
        )
        responses.add(
            responses.GET,
            "https://api.cognitive.microsofttranslator.com/"
            "languages?api-version=3.0",
            json=MS_SUPPORTED_LANG_RESP,
        )
        responses.add(
            responses.POST,
            "https://api.cognitive.microsofttranslator.com/"
            "translate?api-version=3.0&from=en&to=cs&category=general",
            json=MICROSOFT_RESPONSE,
        )


class MicrosoftTerminologyServiceTest(BaseMachineTranslationTest):
    MACHINE_CLS = MicrosoftTerminologyService
    ENGLISH = "en-us"
    SUPPORTED = "cs-cz"
    EXPECTED_LEN = 2

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        self.mock_response(fail=True)

    def mock_response(self, fail=False):
        def request_callback_get(request):
            headers = {}
            if request.path_url == "/Terminology.svc?wsdl":
                with open(TERMINOLOGY_WDSL, "rb") as handle:
                    return (200, headers, handle.read())
            if request.path_url.startswith("/Terminology.svc?wsdl="):
                suffix = request.path_url[22:]
                with open(TERMINOLOGY_WDSL + "." + suffix, "rb") as handle:
                    return (200, headers, handle.read())
            if request.path_url.startswith("/Terminology.svc?xsd="):
                suffix = request.path_url[21:]
                with open(TERMINOLOGY_WDSL + "." + suffix, "rb") as handle:
                    return (200, headers, handle.read())
            return (500, headers, "")

        def request_callback_post(request):
            headers = {}
            if fail:
                return (500, headers, "")
            if b"GetLanguages" in request.body:
                return (200, headers, TERMINOLOGY_LANGUAGES)
            return (200, headers, TERMINOLOGY_TRANSLATE)

        responses.add_callback(
            responses.GET,
            MST_API_URL,
            callback=request_callback_get,
            content_type="text/xml",
        )
        responses.add_callback(
            responses.POST,
            MST_API_URL,
            callback=request_callback_post,
            content_type="text/xml",
        )


@override_settings(MT_GOOGLE_KEY="KEY")
class GoogleTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = GoogleTranslation
    EXPECTED_LEN = 1

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(responses.GET, GOOGLE_API_ROOT + "languages", body="", status=500)
        responses.add(responses.GET, GOOGLE_API_ROOT, body="", status=500)

    def mock_response(self):
        responses.add(
            responses.GET,
            GOOGLE_API_ROOT + "languages",
            json={
                "data": {
                    "languages": [
                        {"language": "en"},
                        {"language": "iw"},
                        {"language": "cs"},
                    ]
                }
            },
        )
        responses.add(
            responses.GET,
            GOOGLE_API_ROOT,
            json={"data": {"translations": [{"translatedText": "svet"}]}},
        )

    @responses.activate
    def test_ratelimit_set(self):
        """Test manual setting of rate limit."""
        machine = self.MACHINE_CLS()
        machine.delete_cache()
        machine.set_rate_limit()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, 0, machine=machine
        )


@override_settings(
    MT_GOOGLE_CREDENTIALS=GOOGLEV3_KEY, MT_GOOGLE_PROJECT="translating-7586"
)
class GoogleV3TranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = GoogleV3Translation
    EXPECTED_LEN = 1

    @override_settings(MT_GOOGLE_CREDENTIALS=None)
    def test_google_apiv3_bad_config(self):
        with self.assertRaises(MissingConfiguration):
            self.get_machine()

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        raise SkipTest("Not tested")

    def mock_response(self):
        # Mock get supported languages
        patcher = patch.object(
            TranslationServiceClient,
            "get_supported_languages",
            Mock(
                return_value=SupportedLanguages(
                    {
                        "languages": [
                            {"language_code": "cs"},
                            {"language_code": "en"},
                            {"language_code": "es"},
                        ]
                    }
                )
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        # Mock translate
        patcher = patch.object(
            TranslationServiceClient,
            "translate_text",
            Mock(
                return_value=TranslateTextResponse(
                    {"translations": [{"translated_text": "Ahoj"}]}
                ),
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class AmagamaTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = AmagamaTranslation
    EXPECTED_LEN = 1
    SOURCE_TRANSLATED = "Hello"

    def mock_empty(self):
        responses.add(responses.GET, AMAGAMA_LIVE + "/languages/", body="", status=404)
        responses.add(responses.GET, AMAGAMA_LIVE + "/en/cs/unit/Hello", json=[])

    def mock_response(self):
        responses.add(
            responses.GET,
            AMAGAMA_LIVE + "/languages/",
            json={"sourceLanguages": ["en"], "targetLanguages": ["cs"]},
        )
        responses.add(
            responses.GET, AMAGAMA_LIVE + "/en/cs/unit/Hello", json=AMAGAMA_JSON
        )

    def mock_error(self):
        responses.add(responses.GET, AMAGAMA_LIVE + "/languages/", body="", status=404)
        responses.add(
            responses.GET, AMAGAMA_LIVE + "/en/cs/unit/Hello", body="", status=500
        )


@override_settings(MT_YANDEX_KEY="KEY")
class YandexTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = YandexTranslation
    EXPECTED_LEN = 1

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(
            responses.GET,
            "https://translate.yandex.net/api/v1.5/tr.json/getLangs",
            json={"code": 401},
        )
        responses.add(
            responses.GET,
            "https://translate.yandex.net/api/v1.5/tr.json/translate",
            json={"code": 400, "message": "Invalid request"},
        )

    def mock_response(self):
        responses.add(
            responses.GET,
            "https://translate.yandex.net/api/v1.5/tr.json/getLangs",
            json={"langs": {"en": "English", "cs": "Czech"}},
        )
        responses.add(
            responses.GET,
            "https://translate.yandex.net/api/v1.5/tr.json/translate",
            json={"code": 200, "lang": "en-cs", "text": ["svet"]},
        )

    @responses.activate
    def test_error_message(self):
        message = "Invalid test request"
        responses.add(
            responses.GET,
            "https://translate.yandex.net/api/v1.5/tr.json/getLangs",
            json={"langs": {"en": "English", "cs": "Czech"}},
        )
        responses.add(
            responses.GET,
            "https://translate.yandex.net/api/v1.5/tr.json/translate",
            json={"code": 400, "message": message},
        )
        with self.assertRaisesRegex(MachineTranslationError, message):
            self.assert_translate(self.SUPPORTED, self.SOURCE_BLANK, 0)


@override_settings(MT_YOUDAO_ID="id", MT_YOUDAO_SECRET="secret")
class YoudaoTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = YoudaoTranslation
    EXPECTED_LEN = 1
    SUPPORTED = "de"
    NOTSUPPORTED = "cs"
    ENGLISH = "EN"

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(
            responses.GET, "https://openapi.youdao.com/api", json={"errorCode": 1}
        )

    def mock_response(self):
        responses.add(
            responses.GET,
            "https://openapi.youdao.com/api",
            json={"errorCode": 0, "translation": ["hello"]},
        )


@override_settings(MT_NETEASE_KEY="key", MT_NETEASE_SECRET="secret")
class NeteaseSightTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = NeteaseSightTranslation
    EXPECTED_LEN = 1
    SUPPORTED = "zh"

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(responses.POST, NETEASE_API_ROOT, json={"success": "false"})

    def mock_response(self):
        responses.add(
            responses.POST,
            NETEASE_API_ROOT,
            json={
                "success": "true",
                "relatedObject": {"content": [{"transContent": "hello"}]},
            },
        )


@override_settings(MT_BAIDU_ID="id", MT_BAIDU_SECRET="secret")
class BaiduTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = BaiduTranslation
    EXPECTED_LEN = 1
    NOTSUPPORTED = "ia"

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(
            responses.GET, BAIDU_API, json={"error_code": 1, "error_msg": "Error"}
        )

    def mock_response(self):
        responses.add(
            responses.GET,
            BAIDU_API,
            json={"trans_result": [{"src": "hello", "dst": "hallo"}]},
        )

    @responses.activate
    def test_ratelimit(self):
        responses.add(
            responses.GET, BAIDU_API, json={"error_code": "54003", "error_msg": "Error"}
        )
        with self.assertRaises(MachineryRateLimit):
            self.assert_translate(self.SUPPORTED, self.SOURCE_TRANSLATED, 0)

    @responses.activate
    def test_bug(self):
        responses.add(
            responses.GET, BAIDU_API, json={"error_code": "bug", "error_msg": "Error"}
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(self.SUPPORTED, self.SOURCE_TRANSLATED, 0)


@override_settings(MT_SAP_BASE_URL="http://sth.example.com/")
class SAPTranslationHubTest(BaseMachineTranslationTest):
    MACHINE_CLS = SAPTranslationHub
    EXPECTED_LEN = 1

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(
            responses.GET, "http://sth.example.com/languages", body="", status=500
        )
        responses.add(
            responses.POST, "http://sth.example.com/translate", body="", status=500
        )

    def mock_response(self):
        responses.add(
            responses.GET,
            "http://sth.example.com/languages",
            json={
                "languages": [
                    {"id": "en", "name": "English", "bcp-47-code": "en"},
                    {"id": "cs", "name": "Czech", "bcp-47-code": "cs"},
                ]
            },
            status=200,
        )
        responses.add(
            responses.POST,
            "http://sth.example.com/translate",
            json=SAPTRANSLATIONHUB_JSON,
            status=200,
            content_type="text/json",
        )


@override_settings(MT_MODERNMT_KEY="key")
class ModernMTHubTest(BaseMachineTranslationTest):
    MACHINE_CLS = ModernMTTranslation
    EXPECTED_LEN = 1

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(
            responses.GET, "https://api.modernmt.com/languages", body="", status=500
        )
        responses.add(
            responses.GET, "https://api.modernmt.com/translate", body="", status=500
        )

    def mock_response(self):
        responses.add(
            responses.GET,
            "https://api.modernmt.com/languages",
            json={
                "data": {"en": ["cs", "it", "ja"], "fr": ["en", "it", "ja"]},
                "status": 200,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            "https://api.modernmt.com/translate",
            json={
                "data": {
                    "contextVector": {
                        "entries": [
                            {
                                "memory": {"id": 1, "name": "europarl"},
                                "score": 0.20658109,
                            },
                            {"memory": {"id": 2, "name": "ibm"}, "score": 0.0017772929},
                        ]
                    },
                    "translation": "Ciao",
                },
                "status": 200,
            },
            status=200,
            content_type="text/json",
        )


@override_settings(
    MT_SAP_SANDBOX_APIKEY="http://sandbox.example.com",
    MT_SAP_USERNAME="username",
    MT_SAP_PASSWORD="password",
)
class SAPTranslationHubAuthTest(SAPTranslationHubTest):
    pass


@override_settings(MT_DEEPL_KEY="KEY")
class DeepLTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = DeepLTranslation
    EXPECTED_LEN = 1
    ENGLISH = "EN"
    SUPPORTED = "DE"
    NOTSUPPORTED = "CS"

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(
            responses.POST,
            DEEPL_LANGUAGES.format("v2"),
            json=DEEPL_LANG_RESPONSE,
            status=500,
        )
        responses.add(
            responses.POST,
            DEEPL_TRANSLATE.format("v2"),
            json=DEEPL_RESPONSE,
            status=500,
        )

    def mock_response(self):
        responses.add(
            responses.POST, DEEPL_LANGUAGES.format("v2"), json=DEEPL_LANG_RESPONSE
        )
        responses.add(responses.POST, DEEPL_TRANSLATE.format("v2"), json=DEEPL_RESPONSE)

    @responses.activate
    def test_cache(self):
        machine = self.MACHINE_CLS()
        machine.delete_cache()
        self.mock_response()
        # Fetch from service
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 2)
        responses.reset()
        # Fetch from cache
        machine = self.MACHINE_CLS()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 0)


@override_settings(MT_AWS_REGION="us-west-2")
class AWSTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = AWSTranslation
    EXPECTED_LEN = 1
    NOTSUPPORTED = "ia"

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        raise SkipTest("Not tested")

    def mock_response(self):
        pass

    def test_translate(self, **kwargs):
        machine = self.get_machine()
        with Stubber(machine.client) as stubber:
            stubber.add_response(
                "translate_text",
                {
                    "TranslatedText": "Hallo",
                    "SourceLanguageCode": "en",
                    "TargetLanguageCode": "de",
                },
                {"SourceLanguageCode": ANY, "TargetLanguageCode": ANY, "Text": ANY},
            )
            self.assert_translate(
                self.SUPPORTED,
                self.SOURCE_TRANSLATED,
                self.EXPECTED_LEN,
                machine=machine,
            )

    def test_translate_language_map(self, **kwargs):
        machine = self.get_machine()
        with Stubber(machine.client) as stubber:
            stubber.add_response(
                "translate_text",
                {
                    "TranslatedText": "Ahoj",
                    "SourceLanguageCode": "en",
                    "TargetLanguageCode": "cs",
                },
                {"SourceLanguageCode": ANY, "TargetLanguageCode": ANY, "Text": ANY},
            )
            unit = MockUnit(code="cs_CZ", source="Hello")
            unit.translation.component.source_language.code = "en_US"
            translation = machine.translate(unit)
            self.assertIsInstance(translation, list)
            self.assertEqual(
                translation,
                [{"text": "Ahoj", "quality": 88, "service": "AWS", "source": "Hello"}],
            )

    def test_batch(self, machine=None):
        if machine is None:
            machine = self.get_machine()
        with Stubber(machine.client) as stubber:
            stubber.add_response(
                "translate_text",
                {
                    "TranslatedText": "Hallo",
                    "SourceLanguageCode": "en",
                    "TargetLanguageCode": "de",
                },
                {"SourceLanguageCode": ANY, "TargetLanguageCode": ANY, "Text": ANY},
            )
            super().test_batch(machine=machine)


class WeblateTranslationTest(FixtureTestCase):
    @classmethod
    def _databases_support_transactions(cls):
        # This is workaroud for MySQL as FULL TEXT index does not work
        # well inside a transaction, so we avoid using transactions for
        # tests. Otherwise we end up with no matches for the query.
        # See https://dev.mysql.com/doc/refman/5.6/en/innodb-fulltext-index.html
        if not using_postgresql():
            return False
        return super()._databases_support_transactions()

    def test_empty(self):
        machine = WeblateTranslation()
        results = machine.translate(self.get_unit(), self.user)
        self.assertEqual(results, [])

    def test_exists(self):
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        # Create fake fulltext entry
        other = unit.translation.unit_set.exclude(pk=unit.pk)[0]
        other.source = unit.source
        other.target = "Preklad"
        other.state = STATE_TRANSLATED
        other.save()
        # Perform lookup
        machine = WeblateTranslation()
        results = machine.translate(unit, self.user)
        self.assertNotEqual(results, [])
