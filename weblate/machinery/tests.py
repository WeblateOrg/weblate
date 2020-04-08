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


import responses
from botocore.stub import ANY, Stubber
from django.test import TestCase
from django.test.utils import override_settings

from weblate.checks.tests.test_checks import MockUnit
from weblate.machinery.apertium import ApertiumAPYTranslation
from weblate.machinery.aws import AWSTranslation
from weblate.machinery.baidu import BAIDU_API, BaiduTranslation
from weblate.machinery.base import MachineryRateLimit, MachineTranslationError
from weblate.machinery.deepl import DeepLTranslation
from weblate.machinery.dummy import DummyTranslation
from weblate.machinery.glosbe import GlosbeTranslation
from weblate.machinery.google import GOOGLE_API_ROOT, GoogleTranslation
from weblate.machinery.microsoft import MicrosoftCognitiveTranslation
from weblate.machinery.microsoftterminology import (
    MST_API_URL,
    MicrosoftTerminologyService,
)
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

TERMINOLOGY_LANGUAGES = """
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
""".encode()
TERMINOLOGY_TRANSLATE = """
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
""".encode()
TERMINOLOGY_WDSL = get_test_file("microsoftterminology.wsdl")

DEEPL_RESPONSE = {"translations": [{"detected_source_language": "EN", "text": "Hallo"}]}

MICROSOFT_RESPONSE = [{"translations": [{"text": "Svět.", "to": "cs"}]}]

MS_SUPPORTED_LANG_RESP = {"translation": {"cs": "data", "en": "data", "es": "data"}}


class MachineTranslationTest(TestCase):
    """Testing of machine translation core."""

    def get_machine(self, cls, cache=False):
        machine = cls()
        machine.delete_cache()
        machine.cache_translations = cache
        return machine

    def test_support(self):
        machine_translation = self.get_machine(DummyTranslation)
        machine_translation.get_supported_languages()
        self.assertTrue(machine_translation.is_supported("en", "cs"))
        self.assertFalse(machine_translation.is_supported("en", "de"))

    def test_translate(self):
        machine_translation = self.get_machine(DummyTranslation)
        self.assertEqual(
            machine_translation.translate(MockUnit(code="cs", source="Hello")), []
        )
        self.assertEqual(
            len(
                machine_translation.translate(
                    MockUnit(code="cs", source="Hello, world!")
                )
            ),
            2,
        )

    def test_translate_fallback(self):
        machine_translation = self.get_machine(DummyTranslation)
        self.assertEqual(
            len(
                machine_translation.translate(
                    MockUnit(code="cs_CZ", source="Hello, world!")
                )
            ),
            2,
        )

    def test_translate_fallback_missing(self):
        machine_translation = self.get_machine(DummyTranslation)
        self.assertEqual(
            machine_translation.translate(
                MockUnit(code="de_CZ", source="Hello, world!"),
            ),
            [],
        )

    def assert_translate(self, machine, lang="cs", word="world", empty=False):
        translation = machine.translate(MockUnit(code=lang, source=word))
        self.assertIsInstance(translation, list)
        if not empty:
            self.assertTrue(translation)
        for result in translation:
            for key, value in result.items():
                if key == "quality":
                    self.assertIsInstance(
                        value, int, "'{}' is supposed to be a integer".format(key)
                    )
                else:
                    self.assertIsInstance(
                        value, str, "'{}' is supposed to be a string".format(key)
                    )

    @responses.activate
    def test_glosbe(self):
        machine = self.get_machine(GlosbeTranslation)
        responses.add(
            responses.GET, "https://glosbe.com/gapi/translate", json=GLOSBE_JSON
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word="Zkouška")

    @responses.activate
    def test_glosbe_ratelimit(self):
        machine = self.get_machine(GlosbeTranslation)
        responses.add(
            responses.GET,
            "https://glosbe.com/gapi/translate",
            json=GLOSBE_JSON,
            status=429,
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, empty=True)
        self.assert_translate(machine, empty=True)

    @responses.activate
    def test_glosbe_ratelimit_set(self):
        machine = self.get_machine(GlosbeTranslation)
        machine.set_rate_limit()
        responses.add(
            responses.GET, "https://glosbe.com/gapi/translate", json=GLOSBE_JSON
        )
        self.assert_translate(machine, empty=True)

    @override_settings(MT_MYMEMORY_EMAIL="test@weblate.org")
    @responses.activate
    def test_mymemory(self):
        machine = self.get_machine(MyMemoryTranslation)
        responses.add(
            responses.GET, "https://mymemory.translated.net/api/get", json=MYMEMORY_JSON
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word="Zkouška")

    def register_apertium_urls(self):
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

    @override_settings(MT_APERTIUM_APY="http://apertium.example.com/")
    @responses.activate
    def test_apertium_apy(self):
        machine = self.get_machine(ApertiumAPYTranslation)
        self.register_apertium_urls()
        self.assert_translate(machine, "es")
        self.assert_translate(machine, "es", word="Zkouška")

    @override_settings(MT_MICROSOFT_COGNITIVE_KEY="KEY")
    @responses.activate
    def test_microsoft_cognitive(self):
        machine = self.get_machine(MicrosoftCognitiveTranslation)
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

        self.assert_translate(machine)
        self.assert_translate(machine, word="Zkouška")

    @override_settings(
        MT_MICROSOFT_COGNITIVE_KEY="KEY", MT_MICROSOFT_REGION="westeurope"
    )
    @responses.activate
    def test_microsoft_cognitive_with_region(self):
        machine = self.get_machine(MicrosoftCognitiveTranslation)
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

        self.assert_translate(machine)
        self.assert_translate(machine, word="Zkouška")

    def register_microsoft_terminology(self, fail=False):
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

    @responses.activate
    def test_microsoft_terminology(self):
        self.register_microsoft_terminology()
        machine = self.get_machine(MicrosoftTerminologyService)
        self.assert_translate(machine)
        self.assert_translate(machine, lang="cs_CZ")

    @responses.activate
    def test_microsoft_terminology_error(self):
        self.register_microsoft_terminology(True)
        machine = self.get_machine(MicrosoftTerminologyService)
        machine.get_supported_languages()
        self.assertEqual(machine.supported_languages, [])
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, empty=True)

    @override_settings(MT_GOOGLE_KEY="KEY")
    @responses.activate
    def test_google(self):
        machine = self.get_machine(GoogleTranslation)
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
        self.assert_translate(machine)
        self.assert_translate(machine, lang="he")
        self.assert_translate(machine, word="Zkouška")

    @override_settings(MT_GOOGLE_KEY="KEY")
    @responses.activate
    def test_google_invalid(self):
        """Test handling of server failure."""
        machine = self.get_machine(GoogleTranslation)
        responses.add(responses.GET, GOOGLE_API_ROOT + "languages", body="", status=500)
        responses.add(responses.GET, GOOGLE_API_ROOT, body="", status=500)
        machine.get_supported_languages()
        self.assertEqual(machine.supported_languages, [])
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, empty=True)

    @responses.activate
    def test_amagama_nolang(self):
        machine = self.get_machine(AmagamaTranslation)
        responses.add(responses.GET, AMAGAMA_LIVE + "/languages/", body="", status=404)
        responses.add(
            responses.GET, AMAGAMA_LIVE + "/en/cs/unit/world", json=AMAGAMA_JSON
        )
        responses.add(
            responses.GET, AMAGAMA_LIVE + "/en/cs/unit/Zkou%C5%A1ka", json=AMAGAMA_JSON
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word="Zkouška")

    @override_settings(DEBUG=True)
    def test_amagama_nolang_debug(self):
        self.test_amagama_nolang()

    @responses.activate
    def test_amagama(self):
        machine = self.get_machine(AmagamaTranslation)
        responses.add(
            responses.GET,
            AMAGAMA_LIVE + "/languages/",
            json={"sourceLanguages": ["en"], "targetLanguages": ["cs"]},
        )
        responses.add(
            responses.GET, AMAGAMA_LIVE + "/en/cs/unit/world", json=AMAGAMA_JSON
        )
        responses.add(
            responses.GET, AMAGAMA_LIVE + "/en/cs/unit/Zkou%C5%A1ka", json=AMAGAMA_JSON
        )
        self.assert_translate(machine)
        self.assert_translate(machine, word="Zkouška")

    @override_settings(MT_YANDEX_KEY="KEY")
    @responses.activate
    def test_yandex(self):
        machine = self.get_machine(YandexTranslation)
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
        self.assert_translate(machine)
        self.assert_translate(machine, word="Zkouška")

    @override_settings(MT_YANDEX_KEY="KEY")
    @responses.activate
    def test_yandex_error(self):
        machine = self.get_machine(YandexTranslation)
        responses.add(
            responses.GET,
            "https://translate.yandex.net/api/v1.5/tr.json/getLangs",
            json={"code": 401},
        )
        responses.add(
            responses.GET,
            "https://translate.yandex.net/api/v1.5/tr.json/translate",
            json={"code": 401, "message": "Invalid request"},
        )
        machine.get_supported_languages()
        self.assertEqual(machine.supported_languages, [])
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, empty=True)

    @override_settings(MT_YOUDAO_ID="id", MT_YOUDAO_SECRET="secret")
    @responses.activate
    def test_youdao(self):
        machine = self.get_machine(YoudaoTranslation)
        responses.add(
            responses.GET,
            "https://openapi.youdao.com/api",
            json={"errorCode": 0, "translation": ["hello"]},
        )
        self.assert_translate(machine, lang="ja")
        self.assert_translate(machine, lang="ja", word="Zkouška")

    @override_settings(MT_YOUDAO_ID="id", MT_YOUDAO_SECRET="secret")
    @responses.activate
    def test_youdao_error(self):
        machine = self.get_machine(YoudaoTranslation)
        responses.add(
            responses.GET, "https://openapi.youdao.com/api", json={"errorCode": 1}
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, lang="ja", empty=True)

    @override_settings(MT_NETEASE_KEY="key", MT_NETEASE_SECRET="secret")
    @responses.activate
    def test_netease(self):
        machine = self.get_machine(NeteaseSightTranslation)
        responses.add(
            responses.POST,
            NETEASE_API_ROOT,
            json={
                "success": "true",
                "relatedObject": {"content": [{"transContent": "hello"}]},
            },
        )
        self.assert_translate(machine, lang="zh")
        self.assert_translate(machine, lang="zh", word="Zkouška")

    @override_settings(MT_NETEASE_KEY="key", MT_NETEASE_SECRET="secret")
    @responses.activate
    def test_netease_error(self):
        machine = self.get_machine(NeteaseSightTranslation)
        responses.add(responses.POST, NETEASE_API_ROOT, json={"success": "false"})
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, lang="zh", empty=True)

    @override_settings(MT_BAIDU_ID="id", MT_BAIDU_SECRET="secret")
    @responses.activate
    def test_baidu(self):
        machine = self.get_machine(BaiduTranslation)
        responses.add(
            responses.GET,
            BAIDU_API,
            json={"trans_result": [{"src": "hello", "dst": "hallo"}]},
        )
        self.assert_translate(machine, lang="ja")
        self.assert_translate(machine, lang="ja", word="Zkouška")

    @override_settings(MT_BAIDU_ID="id", MT_BAIDU_SECRET="secret")
    @responses.activate
    def test_baidu_error(self):
        machine = self.get_machine(BaiduTranslation)
        responses.add(
            responses.GET, BAIDU_API, json={"error_code": 1, "error_msg": "Error"}
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, lang="ja", empty=True)

    @override_settings(MT_BAIDU_ID="id", MT_BAIDU_SECRET="secret")
    @responses.activate
    def test_baidu_error_bug(self):
        machine = self.get_machine(BaiduTranslation)
        responses.add(
            responses.GET, BAIDU_API, json={"error_code": "bug", "error_msg": "Error"}
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, lang="ja", empty=True)

    @override_settings(MT_BAIDU_ID="id", MT_BAIDU_SECRET="secret")
    @responses.activate
    def test_baidu_error_rate(self):
        machine = self.get_machine(BaiduTranslation)
        responses.add(
            responses.GET, BAIDU_API, json={"error_code": "54003", "error_msg": "Error"}
        )
        with self.assertRaises(MachineryRateLimit):
            self.assert_translate(machine, lang="ja", empty=True)

    @override_settings(MT_SAP_BASE_URL="http://sth.example.com/")
    @override_settings(MT_SAP_SANDBOX_APIKEY="http://sandbox.example.com")
    @override_settings(MT_SAP_USERNAME="username")
    @override_settings(MT_SAP_PASSWORD="password")
    @responses.activate
    def test_saptranslationhub(self):
        machine = self.get_machine(SAPTranslationHub)
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
        self.assert_translate(machine)
        self.assert_translate(machine, word="Zkouška")

    @override_settings(MT_SAP_BASE_URL="http://sth.example.com/")
    @responses.activate
    def test_saptranslationhub_invalid(self):
        machine = self.get_machine(SAPTranslationHub)
        responses.add(
            responses.GET, "http://sth.example.com/languages", body="", status=500
        )
        responses.add(
            responses.POST, "http://sth.example.com/translate", body="", status=500
        )
        machine.get_supported_languages()
        self.assertEqual(machine.supported_languages, [])
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(machine, empty=True)

    @override_settings(MT_DEEPL_KEY="KEY")
    @responses.activate
    def test_deepl(self):
        machine = self.get_machine(DeepLTranslation)
        responses.add(
            responses.POST, "https://api.deepl.com/v1/translate", json=DEEPL_RESPONSE
        )
        self.assert_translate(machine, lang="de", word="Hello")

    @override_settings(MT_DEEPL_KEY="KEY")
    @responses.activate
    def test_cache(self):
        machine = self.get_machine(DeepLTranslation, True)
        responses.add(
            responses.POST, "https://api.deepl.com/v1/translate", json=DEEPL_RESPONSE
        )
        # Fetch from service
        self.assert_translate(machine, lang="de", word="Hello")
        self.assertEqual(len(responses.calls), 1)
        responses.reset()
        # Fetch from cache
        self.assert_translate(machine, lang="de", word="Hello")
        self.assertEqual(len(responses.calls), 0)

    @override_settings(MT_AWS_REGION="us-west-2")
    def test_aws(self):
        machine = self.get_machine(AWSTranslation)
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
            self.assert_translate(machine, lang="de", word="Hello")

    @override_settings(MT_APERTIUM_APY="http://apertium.example.com/")
    @responses.activate
    def test_languages_cache(self):
        machine = self.get_machine(ApertiumAPYTranslation, True)
        self.register_apertium_urls()
        self.assert_translate(machine, "es")
        self.assert_translate(machine, "es", word="Zkouška")
        self.assertEqual(len(responses.calls), 3)
        responses.reset()
        # New instance should use cached languages
        machine = ApertiumAPYTranslation()
        self.assert_translate(machine, "es")
        self.assertEqual(len(responses.calls), 0)


class WeblateTranslationTest(FixtureTestCase):
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
