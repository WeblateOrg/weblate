#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

import json
from copy import copy
from typing import Type
from unittest import SkipTest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

import responses
from botocore.stub import ANY, Stubber
from django.test import TestCase
from django.urls import reverse
from google.cloud.translate_v3 import (
    SupportedLanguages,
    TranslateTextResponse,
    TranslationServiceClient,
)

import weblate.machinery.models
from weblate.checks.tests.test_checks import MockUnit
from weblate.configuration.models import Setting
from weblate.machinery.apertium import ApertiumAPYTranslation
from weblate.machinery.aws import AWSTranslation
from weblate.machinery.baidu import BAIDU_API, BaiduTranslation
from weblate.machinery.base import (
    MachineryRateLimit,
    MachineTranslation,
    MachineTranslationError,
)
from weblate.machinery.deepl import DeepLTranslation
from weblate.machinery.dummy import DummyTranslation
from weblate.machinery.glosbe import GlosbeTranslation
from weblate.machinery.google import GOOGLE_API_ROOT, GoogleTranslation
from weblate.machinery.googlev3 import GoogleV3Translation
from weblate.machinery.libretranslate import LibreTranslateTranslation
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
from weblate.trans.models import Project, Unit
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.classloader import load_class
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

with open(get_test_file("googlev3.json")) as handle:
    GOOGLEV3_KEY = handle.read()

DEEPL_RESPONSE = {"translations": [{"detected_source_language": "EN", "text": "Hallo"}]}
DEEPL_LANG_RESPONSE = [
    {"language": "EN", "name": "English"},
    {"language": "DE", "name": "Deutsch"},
]

LIBRETRANSLATE_TRANS_RESPONSE = {"translatedText": "¡Hola, Mundo!"}
LIBRETRANSLATE_TRANS_ERROR_RESPONSE = {
    "error": "Please contact the server operator to obtain an API key"
}
LIBRETRANSLATE_LANG_RESPONSE = [
    {"code": "en", "name": "English"},
    {"code": "ar", "name": "Arabic"},
    {"code": "zh", "name": "Chinese"},
    {"code": "fr", "name": "French"},
    {"code": "de", "name": "German"},
    {"code": "hi", "name": "Hindi"},
    {"code": "ga", "name": "Irish"},
    {"code": "it", "name": "Italian"},
    {"code": "ja", "name": "Japanese"},
    {"code": "ko", "name": "Korean"},
    {"code": "pt", "name": "Portuguese"},
    {"code": "ru", "name": "Russian"},
    {"code": "es", "name": "Spanish"},
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
    CONFIGURATION = {}

    def get_machine(self, cache=False):
        machine = self.MACHINE_CLS(self.CONFIGURATION)
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

    def assert_translate(
        self, lang, word, expected_len, machine=None, cache=False, unit_args=None
    ):
        if unit_args is None:
            unit_args = {}
        if machine is None:
            machine = self.get_machine(cache=cache)
        translation = machine.translate(MockUnit(code=lang, source=word, **unit_args))
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
            machine_translation.cleanup_text(unit), ("Hello, [X7X]!", {"[X7X]": "%s"})
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
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, 0, machine=machine
        )

    @responses.activate
    def test_ratelimit_set(self):
        """Test manual setting of rate limit."""
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        machine.set_rate_limit()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, 0, machine=machine
        )


class MyMemoryTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = MyMemoryTranslation
    EXPECTED_LEN = 3
    NOTSUPPORTED = "ia"
    CONFIGURATION = {
        "email": "test@weblate.org",
        "username": "user",
        "key": "key",
    }

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        raise SkipTest("Not tested")

    def mock_response(self):
        responses.add(
            responses.GET, "https://mymemory.translated.net/api/get", json=MYMEMORY_JSON
        )


class ApertiumAPYTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = ApertiumAPYTranslation
    ENGLISH = "eng"
    SUPPORTED = "spa"
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "url": "http://apertium.example.com",
    }

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
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 2)
        responses.reset()
        # New instance should use cached languages and translations
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 0)


class MicrosoftCognitiveTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = MicrosoftCognitiveTranslation
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "key": "KEY",
        "endpoint_url": "api.cognitive.microsoft.com",
        "base_url": "api.cognitive.microsofttranslator.com",
        "region": "",
    }

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


class MicrosoftCognitiveTranslationRegionTest(MicrosoftCognitiveTranslationTest):
    CONFIGURATION = {
        "key": "KEY",
        "endpoint_url": "api.cognitive.microsoft.com",
        "base_url": "api.cognitive.microsofttranslator.com",
        "region": "westeurope",
    }

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


class GoogleTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = GoogleTranslation
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "key": "KEY",
    }

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
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        machine.set_rate_limit()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, 0, machine=machine
        )


class GoogleV3TranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = GoogleV3Translation
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "project": "translating-7586",
        "location": "global",
        "credentials": GOOGLEV3_KEY,
    }

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


class YandexTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = YandexTranslation
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "key": "KEY",
    }

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


class YoudaoTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = YoudaoTranslation
    EXPECTED_LEN = 1
    SUPPORTED = "de"
    NOTSUPPORTED = "cs"
    ENGLISH = "EN"
    CONFIGURATION = {
        "key": "id",
        "secret": "secret",
    }

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


class NeteaseSightTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = NeteaseSightTranslation
    EXPECTED_LEN = 1
    SUPPORTED = "zh"
    CONFIGURATION = {"key": "id", "secret": "secret"}

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


class BaiduTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = BaiduTranslation
    EXPECTED_LEN = 1
    NOTSUPPORTED = "ia"
    CONFIGURATION = {
        "key": "id",
        "secret": "secret",
    }

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


class SAPTranslationHubTest(BaseMachineTranslationTest):
    MACHINE_CLS = SAPTranslationHub
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "key": "",
        "username": "",
        "password": "",
        "enable_mt": False,
        "url": "http://sth.example.com/",
    }

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


class SAPTranslationHubAuthTest(SAPTranslationHubTest):
    CONFIGURATION = {
        "key": "id",
        "username": "username",
        "password": "password",
        "url": "http://sth.example.com/",
        "enable_mt": False,
    }


class ModernMTHubTest(BaseMachineTranslationTest):
    MACHINE_CLS = ModernMTTranslation
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "key": "KEY",
        "url": "https://api.modernmt.com/",
    }

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


class DeepLTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = DeepLTranslation
    EXPECTED_LEN = 1
    ENGLISH = "EN"
    SUPPORTED = "DE"
    NOTSUPPORTED = "CS"
    CONFIGURATION = {
        "key": "KEY",
        "url": "https://api.deepl.com/v2/",
    }

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(
            responses.POST,
            "https://api.deepl.com/v2/languages",
            json=DEEPL_LANG_RESPONSE,
            status=500,
        )
        responses.add(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            json=DEEPL_RESPONSE,
            status=500,
        )

    def mock_languages(self):
        responses.add(
            responses.POST,
            "https://api.deepl.com/v2/languages",
            json=DEEPL_LANG_RESPONSE,
        )

    def mock_response(self):
        self.mock_languages()
        responses.add(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            json=DEEPL_RESPONSE,
        )

    @responses.activate
    def test_formality(self):
        def request_callback(request):
            headers = {}
            payload = parse_qs(request.body)
            self.assertIn("formality", payload)
            return (200, headers, json.dumps(DEEPL_RESPONSE))

        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_languages()
        responses.add_callback(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            callback=request_callback,
        )
        # Fetch from service
        self.assert_translate(
            "DE@FORMAL", self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assert_translate(
            "DE@INFORMAL", self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )

    @responses.activate
    def test_replacements(self):
        def request_callback(request):
            headers = {}
            payload = parse_qs(request.body)
            self.assertEqual(payload["text"], ['Hello, <x id="7"></x>!'])
            return (200, headers, json.dumps(DEEPL_RESPONSE))

        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_languages()
        responses.add_callback(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            callback=request_callback,
        )
        # Fetch from service
        self.assert_translate(
            self.SUPPORTED,
            "Hello, %s!",
            self.EXPECTED_LEN,
            machine=machine,
            unit_args={"flags": "python-format"},
        )

    @responses.activate
    def test_cache(self):
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_response()
        # Fetch from service
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 2)
        responses.reset()
        # Fetch from cache
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 0)


class LibreTranslateTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = LibreTranslateTranslation
    EXPECTED_LEN = 1
    ENGLISH = "en"
    SUPPORTED = "es"
    NOTSUPPORTED = "cs"
    CONFIGURATION = {
        "url": "https://libretranslate.com/",
        "key": "",
    }

    def mock_empty(self):
        raise SkipTest("Not tested")

    def mock_error(self):
        responses.add(
            responses.POST,
            "https://libretranslate.com/translate",
            json=LIBRETRANSLATE_TRANS_ERROR_RESPONSE,
            status=403,
        )

    def mock_response(self):
        responses.add(
            responses.GET,
            "https://libretranslate.com/languages",
            json=LIBRETRANSLATE_LANG_RESPONSE,
        )
        responses.add(
            responses.POST,
            "https://libretranslate.com/translate",
            json=LIBRETRANSLATE_TRANS_RESPONSE,
        )

    @responses.activate
    def test_cache(self):
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_response()
        # Fetch from service
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 2)
        responses.reset()
        # Fetch from cache
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 0)


class AWSTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = AWSTranslation
    EXPECTED_LEN = 1
    NOTSUPPORTED = "ia"
    CONFIGURATION = {
        "region": "us-west-2",
        "key": "key",
        "secret": "secret",
    }

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
        machine = WeblateTranslation({})
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
        machine = WeblateTranslation({})
        results = machine.translate(unit, self.user)
        self.assertNotEqual(results, [])


class ViewsTest(FixtureTestCase):
    """Testing of AJAX/JS views."""

    @staticmethod
    def ensure_dummy_mt():
        """Ensure we have dummy mt installed."""
        name = "weblate.machinery.dummy.DummyTranslation"
        service = load_class(name, "TEST")
        if service.get_identifier() not in weblate.machinery.models.MACHINERY:
            weblate.machinery.models.MACHINERY[service.get_identifier()] = service
        Setting.objects.create(
            category=Setting.CATEGORY_MT, name=service.get_identifier(), value={}
        )
        return service

    def test_translate(self):
        self.ensure_dummy_mt()
        unit = self.get_unit()
        response = self.client.post(
            reverse("js-translate", kwargs={"unit_id": unit.id, "service": "dummy"})
        )
        self.assertContains(response, "Ahoj")
        data = response.json()
        self.assertEqual(
            data["translations"],
            [
                {
                    "quality": 100,
                    "service": "Dummy",
                    "text": "Nazdar světe!",
                    "source": "Hello, world!\n",
                },
                {
                    "quality": 100,
                    "service": "Dummy",
                    "text": "Ahoj světe!",
                    "source": "Hello, world!\n",
                },
            ],
        )

        # Invalid service
        response = self.client.post(
            reverse("js-translate", kwargs={"unit_id": unit.id, "service": "invalid"})
        )
        self.assertEqual(response.status_code, 404)

    def test_memory(self):
        unit = self.get_unit()
        url = reverse("js-memory", kwargs={"unit_id": unit.id})
        # Missing param
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        # Valid query
        response = self.client.post(url, {"q": "a"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["service"], "Weblate Translation Memory")

    def test_configure_global(self):
        service = self.ensure_dummy_mt()
        list_url = reverse("machinery-list")
        edit_url = reverse(
            "machinery-edit", kwargs={"machinery": service.get_identifier()}
        )
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 403)

        self.user.is_superuser = True
        self.user.save()

        response = self.client.get(list_url)
        self.assertContains(response, edit_url)

        self.client.post(edit_url, {"delete": "1"})
        self.assertFalse(
            Setting.objects.filter(
                category=Setting.CATEGORY_MT, name=service.get_identifier()
            ).exists()
        )
        self.client.post(edit_url, {"install": "1"})
        self.assertTrue(
            Setting.objects.filter(
                category=Setting.CATEGORY_MT, name=service.get_identifier()
            ).exists()
        )

    def test_configure_project(self):
        service = self.ensure_dummy_mt()
        list_url = reverse("machinery-list", kwargs={"project": self.project.slug})
        edit_url = reverse(
            "machinery-edit",
            kwargs={
                "project": self.project.slug,
                "machinery": service.get_identifier(),
            },
        )
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 403)

        self.make_manager()

        response = self.client.get(list_url)
        self.assertContains(response, edit_url)

        self.client.post(edit_url, {"delete": "1"})
        self.assertTrue(
            Setting.objects.filter(
                category=Setting.CATEGORY_MT, name=service.get_identifier()
            ).exists()
        )
        project = Project.objects.get(pk=self.project.id)
        self.assertEqual(project.machinery_settings["dummy"], None)
        self.client.post(edit_url, {"enable": "1"})
        self.assertTrue(
            Setting.objects.filter(
                category=Setting.CATEGORY_MT, name=service.get_identifier()
            ).exists()
        )
        project = Project.objects.get(pk=self.component.project_id)
        self.assertNotIn("dummy", project.machinery_settings)
