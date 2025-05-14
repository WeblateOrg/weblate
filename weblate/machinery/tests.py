# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import re
from copy import copy
from datetime import UTC, datetime
from functools import partial
from io import StringIO
from typing import TYPE_CHECKING, NoReturn
from unittest.mock import MagicMock, Mock, call, patch

import httpx
import responses
import respx
from aliyunsdkcore.client import AcsClient
from botocore.stub import ANY, Stubber
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from google.api_core import exceptions as google_api_exceptions
from google.cloud.translate import (
    SupportedLanguages,
    TranslateTextResponse,
    TranslationServiceClient,
)

import weblate.machinery.models
from weblate.checks.tests.test_checks import MockUnit
from weblate.configuration.models import Setting, SettingCategory
from weblate.glossary.models import render_glossary_units_tsv
from weblate.lang.models import Language
from weblate.machinery.alibaba import AlibabaTranslation
from weblate.machinery.apertium import ApertiumAPYTranslation
from weblate.machinery.aws import AWSTranslation
from weblate.machinery.baidu import BAIDU_API, BaiduTranslation
from weblate.machinery.base import (
    BatchMachineTranslation,
    MachineryRateLimitError,
    MachineTranslationError,
    SettingsDict,
)
from weblate.machinery.cyrtranslit import CyrTranslitTranslation
from weblate.machinery.deepl import DeepLTranslation
from weblate.machinery.dummy import DummyGlossaryTranslation, DummyTranslation
from weblate.machinery.glosbe import GlosbeTranslation
from weblate.machinery.google import GOOGLE_API_ROOT, GoogleTranslation
from weblate.machinery.googlev3 import GoogleV3Translation
from weblate.machinery.ibm import IBMTranslation
from weblate.machinery.libretranslate import LibreTranslateTranslation
from weblate.machinery.microsoft import MicrosoftCognitiveTranslation
from weblate.machinery.modernmt import ModernMTTranslation
from weblate.machinery.mymemory import MyMemoryTranslation
from weblate.machinery.netease import NETEASE_API_ROOT, NeteaseSightTranslation
from weblate.machinery.openai import AzureOpenAITranslation, OpenAITranslation
from weblate.machinery.saptranslationhub import SAPTranslationHub
from weblate.machinery.systran import SystranTranslation
from weblate.machinery.tmserver import TMServerTranslation
from weblate.machinery.weblatetm import WeblateTranslation
from weblate.machinery.yandex import YandexTranslation
from weblate.machinery.yandexv2 import YandexV2Translation
from weblate.machinery.youdao import YoudaoTranslation
from weblate.trans.models import Project, Unit
from weblate.trans.tests.test_views import FixtureTestCase, ViewTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.classloader import load_class
from weblate.utils.db import TransactionsTestMixin
from weblate.utils.state import STATE_TRANSLATED

from .types import SourceLanguageChoices

if TYPE_CHECKING:
    from requests import PreparedRequest

AMAGAMA_LIVE = "https://amagama-live.translatehouse.org/api/v1"

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
SYSTRAN_LANGUAGE_JSON = {
    "languagePairs": [
        {
            "source": "en",
            "target": "cs",
            "profiles": [
                {
                    "id": "32e871bd-c82f-4b36-a59f-7cfd109a606e",
                    "private": False,
                    "selectors": {
                        "domain": "Generic",
                        "owner": "Systran",
                        "size": "L",
                        "tech": {"name": "OpenNMT-ctranslate", "type": "NMT"},
                    },
                },
                {
                    "id": "4c02852a-54f4-4c26-81c1-271c71fea810",
                    "private": False,
                    "selectors": {
                        "domain": "Cybersecurity",
                        "owner": "Systran",
                        "size": "L",
                        "tech": {"name": "OpenNMT-ctranslate", "type": "NMT"},
                    },
                },
            ],
        },
    ],
}

with open(get_test_file("googlev3.json")) as handle:
    GOOGLEV3_KEY = handle.read()

MODERNMT_REPONSE = {
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
}

DEEPL_RESPONSE = {"translations": [{"detected_source_language": "EN", "text": "Hallo"}]}
DEEPL_LANG_RESPONSE = [
    {"language": "EN", "name": "English"},
    {"language": "DE", "name": "Deutsch", "supports_formality": True},
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

MS_SUPPORTED_LANG_RESP = {
    "translation": {"cs": "data", "en": "data", "es": "data", "de": "data"}
}

AWS_LANGUAGES_RESPONSE = {
    "Languages": [
        {"LanguageName": "Afrikaans", "LanguageCode": "af"},
        {"LanguageName": "Czech", "LanguageCode": "cs"},
        {"LanguageName": "German", "LanguageCode": "de"},
        {"LanguageName": "English", "LanguageCode": "en"},
    ]
}


class BaseMachineTranslationTest(TestCase):
    """Testing of machine translation core."""

    MACHINE_CLS: type[BatchMachineTranslation] = DummyTranslation
    ENGLISH = "en"
    SUPPORTED = "cs"
    SUPPORTED_VARIANT = "cs_CZ"
    NOTSUPPORTED: str | None = "tg"
    NOTSUPPORTED_VARIANT = "fr_CZ"
    SOURCE_BLANK = "Hello"
    SOURCE_TRANSLATED = "Hello, world!"
    EXPECTED_LEN = 2
    CONFIGURATION: SettingsDict = {}

    def get_machine(self, cache=False):
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        machine.cache_translations = cache
        return machine

    @responses.activate
    @respx.mock
    def test_validate_settings(self) -> None:
        self.mock_response()
        machine = self.get_machine()
        machine.validate_settings()

    def test_english_map(self) -> None:
        machine = self.get_machine()
        self.assertEqual(machine.map_language_code("en_devel"), self.ENGLISH)

    @responses.activate
    @respx.mock
    def test_support(self, machine_translation=None) -> None:
        self.mock_response()
        if machine_translation is None:
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
        for items in translation:
            self.assertEqual(len(items), expected_len)
            self.assertIsInstance(items, list)
            for result in items:
                for key, value in result.items():
                    if key == "quality":
                        self.assertIsInstance(
                            value, int, f"{key!r} is supposed to be a integer"
                        )
                    elif key == "show_quality":
                        self.assertIsInstance(
                            value, bool, f"{key!r} is supposed to be a boolean"
                        )
                    else:
                        self.assertIsInstance(
                            value, str, f"{key!r} is supposed to be a string"
                        )
        return translation

    def mock_empty(self) -> None:
        pass

    def mock_response(self) -> None:
        pass

    def mock_error(self) -> None:
        self.skipTest("Not tested")

    @responses.activate
    @respx.mock
    def test_translate_empty(self) -> None:
        self.mock_empty()
        self.assert_translate(self.SUPPORTED, self.SOURCE_BLANK, 0)

    @responses.activate
    @respx.mock
    def test_translate(self, **kwargs) -> None:
        self.mock_response()
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, **kwargs
        )

    @responses.activate
    @respx.mock
    def test_batch(self, machine=None) -> None:
        self.mock_response()
        if machine is None:
            machine = self.get_machine()
        unit1 = MockUnit(
            code=self.SUPPORTED, source=self.SOURCE_TRANSLATED, target="target"
        )
        unit2 = MockUnit(code=self.SUPPORTED, source=self.SOURCE_TRANSLATED)
        unit2.translated = False
        machine.batch_translate([unit1, unit2])
        self.assertGreater(unit1.machinery["quality"][0], -1)
        self.assertIn("translation", unit1.machinery)
        self.assertGreater(unit2.machinery["quality"][0], -1)
        self.assertIn("translation", unit2.machinery)

    @responses.activate
    @respx.mock
    def test_error(self) -> None:
        self.mock_error()
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(self.SUPPORTED, self.SOURCE_BLANK, 0)

    @responses.activate
    @respx.mock
    def test_clean(self) -> None:
        if not self.CONFIGURATION or self.MACHINE_CLS.settings_form is None:
            return
        self.mock_response()
        form = self.MACHINE_CLS.settings_form(self.MACHINE_CLS, self.CONFIGURATION)
        if not form.is_valid():
            self.assertDictEqual(form.errors, {})


class MachineTranslationTest(BaseMachineTranslationTest):
    def test_translate_fallback(self) -> None:
        machine_translation = self.get_machine()
        self.assertEqual(
            len(
                machine_translation.translate(
                    MockUnit(code=self.SUPPORTED_VARIANT, source=self.SOURCE_TRANSLATED)
                )[0],
            ),
            self.EXPECTED_LEN,
        )

    def test_translate_fallback_missing(self) -> None:
        machine_translation = self.get_machine()
        self.assertEqual(
            machine_translation.translate(
                MockUnit(code=self.NOTSUPPORTED_VARIANT, source=self.SOURCE_TRANSLATED)
            ),
            [],
        )

    def test_placeholders(self) -> None:
        machine_translation = self.get_machine()
        unit = MockUnit(code="cs", source="Hello, %s!", flags="c-format")
        self.assertEqual(
            machine_translation.cleanup_text(unit.source, unit),
            ("Hello, [X7X]!", {"[X7X]": "%s"}),
        )
        self.assertEqual(
            machine_translation.translate(unit),
            [
                [
                    {
                        "quality": 100,
                        "service": "Dummy",
                        "source": "Hello, %s!",
                        "original_source": "Hello, %s!",
                        "text": "Nazdar %s!",
                    }
                ]
            ],
        )

    def test_batch(self) -> None:
        machine_translation = self.get_machine()
        units = [
            MockUnit(code="cs", source="Hello, %s!", flags="c-format"),
            MockUnit(code="cs", source="Hello, %d!", flags="c-format"),
        ]
        machine_translation.batch_translate(units)
        self.assertEqual(units[0].machinery["translation"], ["Nazdar %s!"])
        self.assertEqual(units[1].machinery["translation"], ["Nazdar %d!"])

    def test_key(self) -> None:
        machine_translation = self.get_machine()
        self.assertEqual(
            machine_translation.get_cache_key("test"),
            "mt:dummy:test:11364700946005001116",
        )


class GlossaryTranslationTest(BaseMachineTranslationTest):
    """Test case for glossary translation functionality."""

    MACHINE_CLS = DummyGlossaryTranslation

    @patch("weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar")
    def test_translate(self) -> None:
        """Test glossary translation."""
        machine = self.get_machine()
        self.assertEqual(machine.list_glossaries(), {})
        list_glossaries_patcher = patch.object(
            DummyGlossaryTranslation,
            "list_glossaries",
            Mock(
                side_effect=[
                    # with stale glossary
                    {
                        "weblate:1:en:cs:2d9a814c5f6321a8": "weblate:1:en:cs:2d9a814c5f6321a8"
                    },
                    # with new glossary
                    {
                        "weblate:1:en:cs:9e250d830c11d70f": "weblate:1:en:cs:9e250d830c11d70f"
                    },
                    # with no glossary
                    {},
                ]
            ),
        )
        list_glossaries_patcher.start()
        super().test_translate()
        list_glossaries_patcher.stop()

    def test_glossary_cleanup(self) -> None:
        """
        Test cleanup of glossary TSV content.

        Any problematic leading character is removed from term
        Leading and trailing whitespaces are stripped
        """
        unit = MockUnit(code="cs", source="foo", target="bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")

        # prohibited characters cleaned
        unit = MockUnit(code="cs", source="=foo", target="=bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")
        unit = MockUnit(code="cs", source="+foo", target="+bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")
        unit = MockUnit(code="cs", source="-foo", target="-bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")
        unit = MockUnit(code="cs", source="@foo", target="@bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")
        unit = MockUnit(code="cs", source="|foo", target="|bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")
        unit = MockUnit(code="cs", source="%foo", target="%bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")

        # multiple prohibited characters are cleaned
        unit = MockUnit(code="cs", source="==foo", target="==bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")

        # whitespace correctly stripped
        unit = MockUnit(code="cs", source=" foo  ", target=" bar  ")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")

        # whitespaces after prohibited characters correctly stripped
        unit = MockUnit(code="cs", source="% foo  ", target="% bar  ")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")
        unit = MockUnit(code="cs", source="% foo  ", target="% % bar  ")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")

        # other Unicode whitespaces are correctly stripped
        unit = MockUnit(code="cs", source="\r- foo", target="bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")
        unit = MockUnit(code="cs", source="|\u00a0foo", target="bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")
        unit = MockUnit(code="cs", source="\n\nfoo", target="bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")
        unit = MockUnit(code="cs", source="%\u2002foo  ", target="%bar")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo\tbar")

        # no character cleaned
        unit = MockUnit(code="cs", source="foo=", target="bar=")
        self.assertEqual(render_glossary_units_tsv([unit]), "foo=\tbar=")
        unit = MockUnit(code="cs", source=":foo", target=":bar")
        self.assertEqual(render_glossary_units_tsv([unit]), ":foo\t:bar")

    def test_glossary_changes_invalidates_result_cache(self) -> None:
        machine = self.get_machine(cache=True)
        source_text = "Hello, world!"
        unit = MockUnit(code="cs", source=source_text, target="")

        with (
            patch.object(
                DummyGlossaryTranslation,
                "list_glossaries",
                return_value={
                    "weblate:1:en:cs:9e250d830c11d70f": "weblate:1:en:cs:9e250d830c11d70f"
                },
            ),
            patch("weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar"),
        ):
            machine.translate(unit, threshold=75)
            cache_key, result = machine.get_cached(
                unit, "en", "cs", source_text, 75, {}
            )
            self.assertIsNotNone(cache_key)
            self.assertTrue(len(result) > 0)
            self.assertIsNotNone(result)

        with patch(
            "weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar-edit"
        ):
            new_cache_key, new_result = machine.get_cached(
                unit, "en", "cs", source_text, 75, {}
            )
            self.assertIsNone(new_result)
            self.assertNotEqual(cache_key, new_cache_key)


class GlosbeTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = GlosbeTranslation
    EXPECTED_LEN = 1
    NOTSUPPORTED = None

    def mock_empty(self) -> None:
        response = copy(GLOSBE_JSON)
        response["tuc"] = []
        responses.add(responses.GET, "https://glosbe.com/gapi/translate", json=response)

    def mock_response(self) -> None:
        responses.add(
            responses.GET, "https://glosbe.com/gapi/translate", json=GLOSBE_JSON
        )

    def mock_error(self) -> None:
        responses.add(
            responses.GET,
            "https://glosbe.com/gapi/translate",
            json=GLOSBE_JSON,
            status=429,
        )

    @responses.activate
    def test_ratelimit(self) -> None:
        """Test rate limit response handling."""
        # This raises an exception
        self.test_error()
        # The second call should not perform due to rate limiting being cached
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, 0, machine=machine
        )

    @responses.activate
    def test_ratelimit_set(self) -> None:
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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_response(self) -> None:
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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_response(self) -> None:
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
    def test_validate_settings(self) -> None:
        self.mock_response()
        machine = self.get_machine()
        machine.validate_settings()
        self.assertEqual(len(responses.calls), 2)
        _, call_2 = responses.calls
        self.assertIn("langpair", call_2.request.params)
        self.assertEqual("eng|spa", call_2.request.params["langpair"])

    @responses.activate
    def test_translations_cache(self) -> None:
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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_response(self) -> None:
        responses.add(
            responses.POST,
            "https://api.cognitive.microsoft.com/sts/v1.0/issueToken"
            "?Subscription-Key=KEY",
            body="TOKEN",
        )
        responses.add(
            responses.GET,
            "https://api.cognitive.microsofttranslator.com/languages?api-version=3.0",
            json=MS_SUPPORTED_LANG_RESP,
        )
        responses.add(
            responses.POST,
            "https://api.cognitive.microsofttranslator.com/"
            "translate?api-version=3.0&from=en&to=cs&category=general&textType=html",
            json=MICROSOFT_RESPONSE,
        )
        responses.add(
            responses.POST,
            "https://api.cognitive.microsofttranslator.com/"
            "translate?api-version=3.0&from=en&to=de&category=general&textType=html",
            json=MICROSOFT_RESPONSE,
        )
        responses.add(
            responses.POST,
            "https://api.cognitive.microsofttranslator.com/"
            "translate?api-version=3.0&from=en&to=de&category=&textType=html",
            json=MICROSOFT_RESPONSE,
        )

    def test_map_codes(self) -> None:
        machine = self.get_machine()
        self.assertEqual(machine.map_language_code("zh_Hant"), "zh-Hant")
        self.assertEqual(machine.map_language_code("zh_TW"), "zh-Hant")
        self.assertEqual(machine.map_language_code("fr_CA"), "fr-ca")
        self.assertEqual(machine.map_language_code("iu_Latn"), "iu-Latn")


class MicrosoftCognitiveTranslationRegionTest(MicrosoftCognitiveTranslationTest):
    CONFIGURATION = {
        "key": "KEY",
        "endpoint_url": "api.cognitive.microsoft.com",
        "base_url": "api.cognitive.microsofttranslator.com",
        "region": "westeurope",
    }

    def mock_response(self) -> None:
        responses.add(
            responses.POST,
            "https://westeurope.api.cognitive.microsoft.com/sts/v1.0/issueToken"
            "?Subscription-Key=KEY",
            body="TOKEN",
        )
        responses.add(
            responses.GET,
            "https://api.cognitive.microsofttranslator.com/languages?api-version=3.0",
            json=MS_SUPPORTED_LANG_RESP,
        )
        responses.add(
            responses.POST,
            "https://api.cognitive.microsofttranslator.com/"
            "translate?api-version=3.0&from=en&to=cs&category=general&textType=html",
            json=MICROSOFT_RESPONSE,
        )
        responses.add(
            responses.POST,
            "https://api.cognitive.microsofttranslator.com/"
            "translate?api-version=3.0&from=en&to=de&category=general&textType=html",
            json=MICROSOFT_RESPONSE,
        )
        responses.add(
            responses.POST,
            "https://api.cognitive.microsofttranslator.com/"
            "translate?api-version=3.0&from=en&to=de&category=&textType=html",
            json=MICROSOFT_RESPONSE,
        )


class GoogleTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = GoogleTranslation
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "key": "KEY",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(responses.GET, GOOGLE_API_ROOT + "languages", body="", status=500)
        responses.add(responses.GET, GOOGLE_API_ROOT, body="", status=500)

    def mock_response(self) -> None:
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
    def test_ratelimit_set(self) -> None:
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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_languages(self) -> None:
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

    def mock_response(self) -> None:
        self.mock_languages()

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

    def test_mapping(self) -> None:
        machine = self.get_machine()
        self.assertEqual(
            list(
                machine.get_language_possibilities(Language.objects.get(code="zh_Hant"))
            ),
            ["zh-TW", "zh"],
        )
        self.assertEqual(
            list(
                machine.get_language_possibilities(
                    Language.objects.get(code="zh_Hant_HK")
                )
            ),
            ["zh-Hant-HK", "zh-TW", "zh"],
        )

    def test_replacements(self) -> None:
        machine_translation = self.get_machine()
        unit = MockUnit(code="cs", source="Hello,\n%s!", flags="c-format")
        replaced = 'Hello,<br translate="no"><span translate="no" id="7">%s</span>!'
        replacements = {
            '<br translate="no">': "\n",
            '<span translate="no" id="7">%s</span>': "%s",
        }
        self.assertEqual(
            machine_translation.cleanup_text(unit.source, unit),
            (replaced, replacements),
        )
        self.assertEqual(
            unit.source, machine_translation.uncleanup_text(replacements, replaced)
        )

    # set glossary_count_limit to 1 to also trigger delete_oldest_glossary
    @patch("weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar")
    @patch("weblate.machinery.googlev3.GoogleV3Translation.glossary_count_limit", new=1)
    def test_glossary(self) -> None:
        self.mock_languages()
        self.mock_glossary_responses()
        self.CONFIGURATION["bucket_name"] = "test-bucket"

        self.assert_translate(self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN)

    @patch("weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar")
    @patch("weblate.machinery.googlev3.GoogleV3Translation.glossary_count_limit", new=1)
    def test_glossary_with_exception(self) -> None:
        self.mock_languages()
        self.mock_glossary_responses()
        self.CONFIGURATION["bucket_name"] = "test-bucket"

        mock_blob = self.mock_blob(fail_delete=True)
        mock_bucket = self.mock_bucket(mock_blob)

        with (
            patch.object(
                TranslationServiceClient,
                "create_glossary",
                Mock(
                    side_effect=google_api_exceptions.AlreadyExists(
                        "Glossary already exists"
                    )
                ),
            ),
            patch.object(
                TranslationServiceClient,
                "delete_glossary",
                Mock(
                    side_effect=google_api_exceptions.NotFound("Glossary was not found")
                ),
            ),
            patch(
                "google.cloud.storage.Client", new=self.mock_storage_client(mock_bucket)
            ),
        ):
            self.assert_translate(
                self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN
            )

    @patch("weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar")
    @patch("weblate.machinery.googlev3.GoogleV3Translation.glossary_count_limit", new=1)
    def test_glossary_with_calls_check(self) -> None:
        self.mock_languages()
        self.mock_glossary_responses()
        self.CONFIGURATION["bucket_name"] = "test-bucket"

        with patch(
            "weblate.machinery.googlev3.GoogleV3Translation.delete_glossary"
        ) as delete_glossary_method:
            self.assert_translate(
                self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN
            )
            delete_glossary_method.assert_has_calls(
                [
                    call("weblate__1__en__cs__a85e314d2f7614eb"),
                    call("weblate__1__en__it__2d9a814c5f6321a8"),
                ]
            )

    def mock_glossary_responses(self) -> None:
        """
        Mock the responses for Google Cloud Translate V3 API.

        Patches list_glossaries, create_glossary, delete_glossary, translate_text
        and also the storage client.
        """
        from google.cloud.translate_v3 import Glossary
        from google.oauth2 import service_account

        def _glossary(name: str, submit_time: datetime) -> Glossary:
            """Return a mock Glossary object with given name and submit time."""
            return Glossary(
                display_name=name,
                submit_time=submit_time,
            )

        # Mock list glossaries
        list_glossaries_patcher = patch.object(
            TranslationServiceClient,
            "list_glossaries",
            Mock(
                side_effect=[
                    # with stale glossary and another glossary
                    [
                        _glossary(
                            "weblate__1__en__cs__a85e314d2f7614eb",
                            datetime(2024, 9, 1, tzinfo=UTC),
                        ),
                        _glossary(
                            "weblate__1__en__it__2d9a814c5f6321a8",
                            datetime(2024, 9, 1, tzinfo=UTC),
                        ),
                    ],
                    # the stale glossary has been deleted
                    [
                        _glossary(
                            "weblate__1__en__it__2d9a814c5f6321a8",
                            datetime(2024, 9, 1, tzinfo=UTC),
                        )
                    ],
                    # new glossary
                    [
                        _glossary(
                            "weblate__1__en__cs__9e250d830c11d70f",
                            datetime(2024, 10, 1, tzinfo=UTC),
                        )
                    ],
                ]
            ),
        )
        list_glossaries_patcher.start()
        self.addCleanup(list_glossaries_patcher.stop)

        # Mock create glossary
        create_glossary_patcher = patch.object(
            TranslationServiceClient, "create_glossary", Mock()
        )
        create_glossary_patcher.start()
        self.addCleanup(create_glossary_patcher.stop)

        # Mock delete glossary
        delete_glossary_patcher = patch.object(
            TranslationServiceClient, "delete_glossary", Mock()
        )
        delete_glossary_patcher.start()
        self.addCleanup(delete_glossary_patcher.stop)

        # Mock translate with glossary
        translate_patcher = patch.object(
            TranslationServiceClient,
            "translate_text",
            Mock(
                return_value=TranslateTextResponse(
                    {
                        "translations": [{"translated_text": "Ahoj"}],
                        "glossary_translations": [{"translated_text": "Ahoj"}],
                    }
                ),
            ),
        )
        translate_patcher.start()
        self.addCleanup(translate_patcher.stop)

        get_credentials_patcher = patch.object(
            service_account.Credentials,
            "from_service_account_info",
            return_value=MagicMock(),
        )
        get_credentials_patcher.start()
        self.addCleanup(get_credentials_patcher.stop)

        mock_blob = self.mock_blob()
        mock_bucket = self.mock_bucket(mock_blob)
        patcher = patch(
            "google.cloud.storage.Client", new=self.mock_storage_client(mock_bucket)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def mock_storage_client(self, mock_bucket: type[MagicMock]) -> type[MagicMock]:
        class MockStorageClient(MagicMock):
            def get_bucket(self, *args, **kwargs):
                """google.cloud.storage.Client.get_bucket."""
                return mock_bucket()

        return MockStorageClient

    def mock_bucket(self, mock_blob: type[MagicMock]) -> type[MagicMock]:
        class MockBucket(MagicMock):
            def blob(self, *args, **kwargs):
                """Mock google.cloud.storage.Bucket.blob."""
                return mock_blob()

        return MockBucket

    def mock_blob(self, *args, fail_delete: bool = False, **kwargs) -> type[MagicMock]:
        class MockBlob(MagicMock):
            def upload_from_string(self, *args, **kwargs) -> None:
                """Mock google.cloud.storage.Blob.upload_from_string."""

            def delete(self, *args, **kwargs) -> None:
                """Mock google.cloud.storage.Blob.delete."""
                if fail_delete:
                    faile_message = "Blob file was not found"
                    raise google_api_exceptions.NotFound(faile_message)

        return MockBlob


class TMServerTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = TMServerTranslation
    EXPECTED_LEN = 1
    SOURCE_TRANSLATED = "Hello"
    CONFIGURATION = {
        "url": AMAGAMA_LIVE,
    }

    def mock_empty(self) -> None:
        responses.add(responses.GET, AMAGAMA_LIVE + "/languages/", body="", status=404)
        responses.add(responses.GET, AMAGAMA_LIVE + "/en/cs/unit/Hello", json=[])

    def mock_response(self) -> None:
        responses.add(
            responses.GET,
            AMAGAMA_LIVE + "/languages/",
            json={"sourceLanguages": ["en"], "targetLanguages": ["cs"]},
        )
        responses.add(
            responses.GET, AMAGAMA_LIVE + "/en/cs/unit/Hello", json=AMAGAMA_JSON
        )
        responses.add(
            responses.GET, AMAGAMA_LIVE + "/en/de/unit/test", json=AMAGAMA_JSON
        )

    def mock_error(self) -> None:
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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
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

    def mock_response(self) -> None:
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
    def test_error_message(self) -> None:
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


class YandexV2TranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = YandexV2Translation
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "key": "KEY",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.POST,
            "https://translate.api.cloud.yandex.net/translate/v2/languages",
            json={"code": 401},
        )
        responses.add(
            responses.POST,
            "https://translate.api.cloud.yandex.net/translate/v2/translate",
            json={"code": 400, "message": "Invalid request"},
        )

    def mock_response(self) -> None:
        responses.add(
            responses.POST,
            "https://translate.api.cloud.yandex.net/translate/v2/languages",
            json={
                "languages": [
                    {"code": "cs", "name": "Czech"},
                    {"code": "en", "name": "English"},
                ]
            },
        )
        responses.add(
            responses.POST,
            "https://translate.api.cloud.yandex.net/translate/v2/translate",
            json={"translations": [{"text": "svet", "detectedLanguageCode": "en"}]},
        )

    @responses.activate
    def test_error_message(self) -> None:
        message = "Invalid test request"
        responses.add(
            responses.POST,
            "https://translate.api.cloud.yandex.net/translate/v2/languages",
            json={
                "languages": [
                    {"code": "cs", "name": "Czech"},
                    {"code": "en", "name": "English"},
                ]
            },
        )
        responses.add(
            responses.POST,
            "https://translate.api.cloud.yandex.net/translate/v2/translate",
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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.GET, "https://openapi.youdao.com/api", json={"errorCode": 1}
        )

    def mock_response(self) -> None:
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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(responses.POST, NETEASE_API_ROOT, json={"success": "false"})

    def mock_response(self) -> None:
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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.GET, BAIDU_API, json={"error_code": 1, "error_msg": "Error"}
        )

    def mock_response(self) -> None:
        responses.add(
            responses.GET,
            BAIDU_API,
            json={"trans_result": [{"src": "hello", "dst": "hallo"}]},
        )

    @responses.activate
    def test_ratelimit(self) -> None:
        responses.add(
            responses.GET, BAIDU_API, json={"error_code": "54003", "error_msg": "Error"}
        )
        with self.assertRaises(MachineryRateLimitError):
            self.assert_translate(self.SUPPORTED, self.SOURCE_TRANSLATED, 0)

    @responses.activate
    def test_bug(self) -> None:
        responses.add(
            responses.GET, BAIDU_API, json={"error_code": "bug", "error_msg": "Error"}
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(self.SUPPORTED, self.SOURCE_TRANSLATED, 0)


class SystranTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = SystranTranslation
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "key": "key",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_response(self) -> None:
        responses.add(
            responses.GET,
            "https://api-translate.systran.net/translation/apiVersion",
            json={"version": "2.11.0"},
        )

        responses.add(
            responses.GET,
            "https://api-translate.systran.net/translation/supportedLanguages",
            json=SYSTRAN_LANGUAGE_JSON,
        )

        responses.add(
            responses.POST,
            "https://api-translate.systran.net/translation/text/translate",
            json={"outputs": [{"output": "ahoj"}]},
        )


class SAPTranslationHubTest(BaseMachineTranslationTest):
    MACHINE_CLS = SAPTranslationHub
    EXPECTED_LEN = 1
    CONFIGURATION = {
        "key": "x",
        "username": "",
        "password": "",
        "enable_mt": False,
        "url": "http://sth.example.com/",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.GET, "http://sth.example.com/v1/languages", body="", status=500
        )
        responses.add(
            responses.POST, "http://sth.example.com/v1/translate", body="", status=500
        )

    def mock_response(self) -> None:
        responses.add(
            responses.GET,
            "http://sth.example.com/v1/languages",
            json={
                "languages": [
                    {"id": "en", "name": "English", "bcp-47-code": "en"},
                    {"id": "cs", "name": "Czech", "bcp-47-code": "cs"},
                    {"id": "de", "name": "German", "bcp-47-code": "de"},
                ]
            },
            status=200,
        )
        responses.add(
            responses.POST,
            "http://sth.example.com/v1/translate",
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
    ENGLISH = "en"
    SUPPORTED = "it"
    CONFIGURATION = {
        "key": "KEY",
        "url": "https://api.modernmt.com/",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.GET, "https://api.modernmt.com/languages", body="", status=500
        )
        responses.add(
            responses.GET, "https://api.modernmt.com/translate", body="", status=500
        )

    def mock_languages(self) -> None:
        """Set up mock responses for languages list from ModernMT API."""
        responses.add(
            responses.GET,
            "https://api.modernmt.com/languages",
            json={
                "data": {"en": ["cs", "it", "ja"], "fr": ["en", "it", "ja"]},
                "status": 200,
            },
            status=200,
        )

    def mock_response(self) -> None:
        """Set up mock responses for ModernMT API."""
        self.mock_languages()
        responses.add(
            responses.GET,
            "https://api.modernmt.com/translate",
            json=MODERNMT_REPONSE,
            status=200,
            content_type="text/json",
        )

        self.mock_list_glossaries()

    def mock_list_glossaries(self, *id_name_date: tuple[int, str, str | None]) -> None:
        """Set up mock responses for list of glossaries in ModernMT."""
        data: list[dict] = [
            {
                "id": _id,
                "creationDate": _date or "2021-04-12T15:24:26+00:00",
                "name": _name,
            }
            for _id, _name, _date in id_name_date
        ]
        responses.add(
            responses.GET,
            "https://api.modernmt.com/memories",
            json={
                "status": 200,
                "data": data,
            },
        )

    def mock_create_glossary(self, glossary_id: int, glossary_name: str) -> None:
        """Set up mock responses for creating glossary in ModernMT."""
        # creating the memory
        responses.add(
            responses.POST,
            "https://api.modernmt.com/memories",
            json={
                "status": 200,
                "data": {
                    "id": glossary_id,
                    "creationDate": "2021-04-12T15:24:26+00:00",
                    "name": glossary_name,
                },
            },
        )

        # storing content in memory as glossary
        responses.add(
            responses.POST,
            f"https://api.modernmt.com/memories/{glossary_id}/glossary",
            json={
                "status": 200,
                "data": {
                    "id": "00000000-0000-0000-0000-0000000379fc",
                    "memory": glossary_id,
                    "size": 18818,
                    "progress": 0,
                },
            },
        )

        # list glossaries
        self.mock_list_glossaries(
            (
                glossary_id,
                glossary_name,
                "2021-04-12T15:24:26+00:00",
            )
        )

    @responses.activate
    def test_glossary(self, fail_delete_glossary: bool = False) -> None:
        """Test that glossary is used in translation request when available."""

        def translate_request_callback(request: PreparedRequest):
            """Check 'glossaries' included in request params."""
            self.assertIn("glossaries", request.params)
            return (200, {}, json.dumps(MODERNMT_REPONSE))

        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()

        responses.add_callback(
            responses.GET,
            "https://api.modernmt.com/translate",
            callback=translate_request_callback,
        )

        self.mock_response()

        self.mock_create_glossary(37784, "weblate:1:en:it:9e250d830c11d70f")

        with patch(
            "weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar"
        ):
            self.assert_translate(
                self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN
            )

        # change tsv, check that old memory is deleted and new one is created

        # return current list of glossaries
        self.mock_list_glossaries(*[(37784, "weblate:1:en:it:9e250d830c11d70f", None)])

        def delete_glossary_callback(request: PreparedRequest, expected_id: int):
            """Check that the stale glossary is being deleted."""
            self.assertTrue(request.url.endswith(f"memories/{expected_id}"))
            return (200, {}, "{}")

        responses.add_callback(
            responses.DELETE,
            re.compile(r"https://api.modernmt.com/memories/(\d+)"),
            callback=partial(delete_glossary_callback, expected_id=37784),
        )

        self.mock_create_glossary(37785, "weblate:1:en:it:7d3c463b6bb01e5d")

        with patch(
            "weblate.glossary.models.get_glossary_tsv",
            new=lambda _: "foo\tbar\nnew\tentry",
        ):
            self.assert_translate(
                self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN
            )

        if fail_delete_glossary:
            responses.delete(
                re.compile(r"https://api.modernmt.com/memories/(\d+)"), status=404
            )
        else:
            # stale glossary delete
            responses.add_callback(
                responses.DELETE,
                re.compile(r"https://api.modernmt.com/memories/(\d+)"),
                callback=partial(delete_glossary_callback, expected_id=37785),
            )

            # oldest glossary delete
            responses.add_callback(
                responses.DELETE,
                re.compile(r"https://api.modernmt.com/memories/(\d+)"),
                callback=partial(delete_glossary_callback, expected_id=37782),
            )

        # change count limit, check that the oldest glossary is deleted
        self.mock_list_glossaries(
            (
                37782,
                "weblate:1:en:fr:8c123d830c177e90b",
                "2021-01-12T15:24:26+00:00",
            ),
            (
                37783,
                "weblate:1:en:cs:a85e314d2f7614eb",
                "2021-03-12T15:24:26+00:00",
            ),
            (
                37785,
                "weblate:1:en:it:7d3c463b6bb01e5d",
                "2021-04-12T15:24:26+00:00",
            ),
        )

        self.mock_list_glossaries(
            (
                37782,
                "weblate:1:en:fr:8c123d830c177e90b",
                "2021-01-12T15:24:26+00:00",
            ),
            (
                37783,
                "weblate:1:en:cs:a85e314d2f7614eb",
                "2021-03-12T15:24:26+00:00",
            ),
            (
                37785,
                "weblate:1:en:it:7d3c463b6bb01e5d",
                "2021-04-12T15:24:26+00:00",
            ),
        )

        self.mock_list_glossaries(
            (
                37783,
                "weblate:1:en:cs:a85e314d2f7614eb",
                "2021-03-12T15:24:26+00:00",
            ),
            (
                37785,
                "weblate:1:en:it:54c0ca90b9d0e369",
                "2021-04-12T15:24:26+00:00",
            ),
        )
        with (
            patch(
                "weblate.machinery.modernmt.ModernMTTranslation.glossary_count_limit",
                new=1,
            ),
            patch(
                "weblate.glossary.models.get_glossary_tsv",
                new=lambda _: "foo\tbar\ndifferent\tentry",
            ),
        ):
            self.assert_translate(
                self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN
            )

    def test_glossary_with_delete_fail(self):
        self.test_glossary(fail_delete_glossary=True)

    @responses.activate
    def test_context_vector(self) -> None:
        """Test that context vector is sent with the request when configured."""

        def request_callback(request: PreparedRequest):
            """Check 'context_vector' included in request body."""
            self.assertIn("context_vector", request.params)
            return (200, {}, json.dumps(MODERNMT_REPONSE))

        responses.add_callback(
            responses.GET,
            "https://api.modernmt.com/translate",
            callback=request_callback,
        )
        self.mock_response()

        self.CONFIGURATION["context_vector"] = "1234:0.123"
        self.assert_translate(self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN)

    @responses.activate
    @respx.mock
    def test_clean_custom(self) -> None:
        """Check that validation of context_vector settings works."""
        self.mock_response()
        settings = self.CONFIGURATION.copy()
        machine = self.MACHINE_CLS

        # no context vector
        form = self.MACHINE_CLS.settings_form(machine, settings)
        self.assertTrue(form.is_valid())

        # valid context vector
        settings["context_vector"] = "1234:0.123,456:0.134"
        form = self.MACHINE_CLS.settings_form(machine, settings)
        self.assertTrue(form.is_valid())

        # context_vector couples must be separated by comma
        settings["context_vector"] = "1234:0.123;456:0.134"
        form = self.MACHINE_CLS.settings_form(machine, settings)
        self.assertFalse(form.is_valid())

        # weight can only be 3 digits decimal
        settings["context_vector"] = "1234:0.123,456:0.1345"
        form = self.MACHINE_CLS.settings_form(machine, settings)
        self.assertFalse(form.is_valid())

        # weight cannot be greater than 1
        settings["context_vector"] = "1234:1.123,456:0.1345"
        form = self.MACHINE_CLS.settings_form(machine, settings)
        self.assertFalse(form.is_valid())


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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.GET,
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

    @staticmethod
    def mock_languages() -> None:
        responses.add(
            responses.GET,
            "https://api.deepl.com/v2/languages",
            json=DEEPL_LANG_RESPONSE,
        )
        responses.add(
            responses.GET,
            "https://api.deepl.com/v2/glossary-language-pairs",
            json={
                "supported_languages": [
                    {"source_lang": "de", "target_lang": "en"},
                    {"source_lang": "en", "target_lang": "de"},
                ]
            },
        )

    @classmethod
    def mock_response(cls) -> None:
        cls.mock_languages()
        responses.add(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            json=DEEPL_RESPONSE,
        )

    @responses.activate
    def test_formality(self) -> None:
        expected_formality = "more"

        def request_callback(request: PreparedRequest):
            payload = json.loads(request.body)
            self.assertEqual(payload["formality"], expected_formality)
            return (200, {}, json.dumps(DEEPL_RESPONSE))

        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_languages()
        responses.add_callback(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            callback=request_callback,
        )
        # Fetch from service
        expected_formality = "default"
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        expected_formality = "more"
        self.assert_translate(
            "DE@FORMAL", self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        expected_formality = "less"
        self.assert_translate(
            "DE@INFORMAL", self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )

    @responses.activate
    def test_escaping(self) -> None:
        def request_callback(request: PreparedRequest):
            payload = json.loads(request.body)
            self.assertIn("formality", payload)
            response = DEEPL_RESPONSE.copy()
            response["translations"][0]["text"] = "Hallo&amp;welt"
            return (200, {}, json.dumps(response))

        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_languages()
        responses.add_callback(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            callback=request_callback,
        )
        # Fetch from service
        translation = self.assert_translate(
            self.SUPPORTED, "Hello&world", 1, machine=machine
        )
        self.assertEqual(translation[0][0]["source"], "Hello&world")
        self.assertEqual(translation[0][0]["text"], "Hallo&welt")

    @responses.activate
    @patch("weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar")
    def test_glossary(self) -> None:
        def request_callback(request: PreparedRequest):
            payload = json.loads(request.body)
            self.assertIn("glossary_id", payload)
            return (200, {}, json.dumps(DEEPL_RESPONSE))

        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_languages()
        responses.add_callback(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            callback=request_callback,
        )
        responses.add(
            responses.GET,
            "https://api.deepl.com/v2/glossaries",
            json={"glossaries": []},
        )
        responses.add(
            responses.POST,
            "https://api.deepl.com/v2/glossaries",
        )
        responses.add(
            responses.GET,
            "https://api.deepl.com/v2/glossaries",
            json={
                "glossaries": [
                    {
                        "glossary_id": "def3a26b-3e84-45b3-84ae-0c0aaf3525f7",
                        "name": "weblate:1:EN:DE:9e250d830c11d70f",
                        "ready": True,
                        "source_lang": "EN",
                        "target_lang": "DE",
                        "creation_time": "2021-08-03T14:16:18.329Z",
                        "entry_count": 1,
                    }
                ]
            },
        )
        # Fetch from service
        self.assert_translate(self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN)

    @responses.activate
    @patch("weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar")
    def test_glossary_with_failed_delete(self) -> None:
        """Test handling of glossary deletion failure scenario."""
        with patch(
            "weblate.machinery.deepl.DeepLTranslation.glossary_count_limit",
            new=1,
        ):
            self.mock_languages()
            # list glossaries to find matching name
            responses.get(
                "https://api.deepl.com/v2/glossaries",
                json={
                    "glossaries": [
                        {
                            "glossary_id": "8f54a21b-475f-42c2-bf8d-1a0a9f6543e2",
                            "name": "weblate:1:EN:DE:4a8f2d980d32c9a5",
                            "ready": True,
                            "source_lang": "EN",
                            "target_lang": "DE",
                            "creation_time": "2021-08-02T14:16:18.329Z",
                            "entry_count": 1,
                        }
                    ]
                },
            )
            # list glossaries before deleting
            responses.get(
                "https://api.deepl.com/v2/glossaries",
                json={
                    "glossaries": [
                        {
                            "glossary_id": "8f54a21b-475f-42c2-bf8d-1a0a9f6543e2",
                            "name": "weblate:1:EN:DE:4a8f2d980d32c9a5",
                            "ready": True,
                            "source_lang": "EN",
                            "target_lang": "DE",
                            "creation_time": "2021-08-02T14:16:18.329Z",
                            "entry_count": 1,
                        }
                    ]
                },
            )
            # delete oldest glossary
            responses.delete(
                "https://api.deepl.com/v2/glossaries/8f54a21b-475f-42c2-bf8d-1a0a9f6543e2",
                json={"message": "Invalid or missing glossary id"},
                status=400,
            )
            # create new glossary
            responses.post("https://api.deepl.com/v2/glossaries")
            # list glossaries with new entry
            responses.get(
                "https://api.deepl.com/v2/glossaries",
                json={
                    "glossaries": [
                        {
                            "glossary_id": "def3a26b-3e84-45b3-84ae-0c0aaf3525f7",
                            "name": "weblate:1:EN:DE:9e250d830c11d70f",
                            "ready": True,
                            "source_lang": "EN",
                            "target_lang": "DE",
                            "creation_time": "2021-08-03T14:16:18.329Z",
                            "entry_count": 1,
                        }
                    ]
                },
            )

            responses.post("https://api.deepl.com/v2/translate", json=DEEPL_RESPONSE)
            self.assert_translate(
                self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN
            )

    @responses.activate
    def test_replacements(self) -> None:
        def request_callback(request: PreparedRequest):
            payload = json.loads(request.body)
            self.assertEqual(
                payload["text"], ['Hello, <x id="7"></x>! &lt;&lt;foo&gt;&gt;']
            )
            return (
                200,
                {},
                json.dumps(
                    {
                        "translations": [
                            {
                                "detected_source_language": "EN",
                                "text": 'Hallo, <x id="7"></x>! &lt;&lt;foo&gt;&gt;',
                            }
                        ]
                    }
                ),
            )

        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_languages()
        responses.add_callback(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            callback=request_callback,
        )
        # Fetch from service
        translation = self.assert_translate(
            self.SUPPORTED,
            "Hello, %s! <<foo>>",
            self.EXPECTED_LEN,
            machine=machine,
            unit_args={"flags": "python-format"},
        )
        self.assertEqual(translation[0][0]["text"], "Hallo, %s! <<foo>>")

    @responses.activate
    def test_cache(self) -> None:
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_response()
        # Fetch from service
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 3)
        responses.reset()
        # Fetch from cache
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 0)

    def test_api_url(self) -> None:
        self.assertEqual(
            self.MACHINE_CLS(self.CONFIGURATION).api_base_url,
            "https://api.deepl.com/v2",
        )
        self.assertEqual(
            self.MACHINE_CLS(
                {
                    "key": "KEY:fx",
                    "url": "https://api.deepl.com/v2",
                }
            ).api_base_url,
            "https://api-free.deepl.com/v2",
        )
        self.assertEqual(
            self.MACHINE_CLS(
                {
                    "key": "KEY:fx",
                    "url": "https://example.com/v2",
                }
            ).api_base_url,
            "https://example.com/v2",
        )


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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.POST,
            "https://libretranslate.com/translate",
            json=LIBRETRANSLATE_TRANS_ERROR_RESPONSE,
            status=403,
        )

    def mock_response(self) -> None:
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
    def test_cache(self) -> None:
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

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_response(self) -> None:
        pass

    def test_support(self) -> None:
        machine = self.get_machine()
        machine.delete_cache()
        with Stubber(machine.client) as stubber:
            stubber.add_response(
                "list_languages",
                AWS_LANGUAGES_RESPONSE,
            )
            super().test_support(machine)

    def test_validate_settings(self) -> None:
        machine = self.get_machine()
        with Stubber(machine.client) as stubber:
            stubber.add_response(
                "list_languages",
                AWS_LANGUAGES_RESPONSE,
            )
            stubber.add_response(
                "translate_text",
                {
                    "TranslatedText": "Hallo",
                    "SourceLanguageCode": "en",
                    "TargetLanguageCode": "de",
                },
                {"SourceLanguageCode": ANY, "TargetLanguageCode": ANY, "Text": ANY},
            )
            machine.validate_settings()

    def test_translate(self, **kwargs) -> None:
        machine = self.get_machine()
        with Stubber(machine.client) as stubber:
            stubber.add_response(
                "list_languages",
                AWS_LANGUAGES_RESPONSE,
            )
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

    def test_translate_language_map(self, **kwargs) -> None:
        machine = self.get_machine()
        with Stubber(machine.client) as stubber:
            stubber.add_response(
                "list_languages",
                AWS_LANGUAGES_RESPONSE,
            )
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
                [
                    [
                        {
                            "text": "Ahoj",
                            "quality": 88,
                            "service": "Amazon Translate",
                            "source": "Hello",
                            "original_source": "Hello",
                        }
                    ]
                ],
            )

    def test_batch(self, machine=None) -> None:
        if machine is None:
            machine = self.get_machine()
        with Stubber(machine.client) as stubber:
            stubber.add_response(
                "list_languages",
                AWS_LANGUAGES_RESPONSE,
            )
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

    def test_clean(self) -> NoReturn:
        # Stubbing here is tricky
        self.skipTest("Not tested")

    def setup_stubber_with_glossaries(
        self, machine: BatchMachineTranslation, fail_delete: bool = True
    ) -> Stubber:
        """Set up stubber for translation with glossary test."""
        stubber = Stubber(machine.client)

        stubber.add_response(
            "list_languages",
            AWS_LANGUAGES_RESPONSE,
        )
        # glossary list with stale glossary response
        stubber.add_response(
            "list_terminologies",
            {
                "TerminologyPropertiesList": [
                    {
                        "Name": "weblate_-_1_-_en_-_de_-_a85e314d2f7614eb",
                        "SourceLanguageCode": "en",
                        "TargetLanguageCodes": ["de"],
                        "CreatedAt": "2021-03-03T14:16:18.329Z",
                        "Directionality": "UNI",
                        "Format": "TSV",
                    }
                ]
            },
        )

        # glossary list with stale glossary response
        stubber.add_response(
            "list_terminologies",
            {
                "TerminologyPropertiesList": [
                    {
                        "Name": "weblate_-_1_-_en_-_de_-_a85e314d2f7614eb",
                        "SourceLanguageCode": "en",
                        "TargetLanguageCodes": ["de"],
                        "CreatedAt": "2021-03-03T14:16:18.329Z",
                        "Directionality": "UNI",
                        "Format": "TSV",
                    }
                ]
            },
        )

        # delete stale glossary response
        if fail_delete:
            stubber.add_client_error(
                "delete_terminology", "ResourceNotFoundException", http_status_code=400
            )
        else:
            stubber.add_response(
                "delete_terminology",
                {},
                {"Name": "weblate_-_1_-_en_-_de_-_a85e314d2f7614eb"},
            )

        # create glossary response
        stubber.add_response(
            "import_terminology",
            {
                "AuxiliaryDataLocation": {
                    "Location": "location",
                    "RepositoryType": "type",
                },
                "TerminologyProperties": {},
            },
            {
                "Name": "weblate_-_1_-_en_-_cs_-_9e250d830c11d70f",
                "MergeStrategy": "OVERWRITE",
                "TerminologyData": {
                    "File": b"en\tcs\nfoo\tbar",
                    "Format": "TSV",
                    "Directionality": "UNI",
                },
            },
        )

        # return glossary list with newly created glossary
        stubber.add_response(
            "list_terminologies",
            {
                "TerminologyPropertiesList": [
                    {
                        "Name": "weblate_-_1_-_en_-_cs_-_9e250d830c11d70f",
                        "SourceLanguageCode": "en",
                        "TargetLanguageCodes": ["cs"],
                        "CreatedAt": "2021-08-03T14:16:18.329Z",
                        "Directionality": "UNI",
                        "Format": "TSV",
                    },
                ]
            },
        )

        # translate with glossary
        stubber.add_response(
            "translate_text",
            {
                "TranslatedText": "Ahoj",
                "SourceLanguageCode": "en",
                "TargetLanguageCode": "cs",
                "AppliedTerminologies": [
                    {
                        "Name": "weblate_-_1_-_en_-_cs_-_9e250d830c11d70f",
                        "Terms": [
                            {"SourceText": "foo", "TargetText": "bar"},
                        ],
                    },
                ],
            },
            {
                "SourceLanguageCode": ANY,
                "TargetLanguageCode": ANY,
                "Text": ANY,
                "TerminologyNames": ["weblate_-_1_-_en_-_cs_-_9e250d830c11d70f"],
            },
        )

        return stubber

    def test_glossary(self, fail_delete: bool = False) -> None:
        """Test translation with glossary (terminology)."""
        machine = self.get_machine()

        with (
            patch("weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar"),
            patch(
                "weblate.machinery.aws.AWSTranslation.glossary_count_limit",
                new=1,
            ),
        ):
            stubber = self.setup_stubber_with_glossaries(
                machine, fail_delete=fail_delete
            )
            stubber.activate()
            self.assert_translate(
                self.SUPPORTED,
                self.SOURCE_TRANSLATED,
                self.EXPECTED_LEN,
                machine=machine,
            )
            stubber.deactivate()

    def test_glossary_delete_fail(self) -> None:
        """Test translation with glossary with terminology delete fail."""
        self.test_glossary(fail_delete=True)


class AlibabaTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = AlibabaTranslation
    EXPECTED_LEN = 1
    NOTSUPPORTED = "tog"
    CONFIGURATION = {
        "key": "key",
        "secret": "secret",
        "region": "cn-hangzhou",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_response(self) -> None:
        patcher = patch.object(
            AcsClient,
            "do_action_with_exception",
            Mock(
                return_value=json.dumps(
                    {
                        "RequestId": "14E447CA-B93B-4526-ACD7-42AE13CC2AF6",
                        "Data": {"Translated": "Hello"},
                        "Code": 200,
                    }
                )
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class IBMTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = IBMTranslation
    EXPECTED_LEN = 1
    ENGLISH = "en"
    SUPPORTED = "zh-TW"
    CONFIGURATION = {
        "url": "https://api.region.language-translator.watson.cloud.ibm.com/"
        "instances/id",
        "key": "x",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_response(self) -> None:
        responses.add(
            responses.GET,
            "https://api.region.language-translator.watson.cloud.ibm.com/"
            "instances/id/v3/languages?version=2018-05-01",
            json={
                "languages": [
                    {"language": "en"},
                    {"language": "zh-TW"},
                    {"language": "de"},
                ]
            },
        )
        responses.add(
            responses.POST,
            "https://api.region.language-translator.watson.cloud.ibm.com/"
            "instances/id/v3/translate?version=2018-05-01",
            json={
                "translations": [{"translation": "window"}],
                "word_count": 1,
                "character_count": 6,
            },
        )


class OpenAITranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS: type[BatchMachineTranslation] = OpenAITranslation
    EXPECTED_LEN = 1
    ENGLISH = "en"
    SUPPORTED = "zh-TW"
    NOTSUPPORTED = None
    CONFIGURATION = {
        "key": "x",
        "model": "auto",
        "persona": "",
        "style": "",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_response(self) -> None:
        respx.get("https://api.openai.com/v1/models").mock(
            httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "gpt-3.5-turbo",
                            "object": "model",
                            "created": 1686935002,
                            "owned_by": "openai",
                        }
                    ],
                },
            )
        )
        respx.post(
            "https://api.openai.com/v1/chat/completions",
        ).mock(
            httpx.Response(
                200,
                json={
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "created": 1677652288,
                    "model": "gpt-3.5-turbo",
                    "system_fingerprint": "fp_44709d6fcb",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Ahoj světe",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 9,
                        "completion_tokens": 12,
                        "total_tokens": 21,
                    },
                },
            )
        )


class OpenAICustomTranslationTest(OpenAITranslationTest):
    CONFIGURATION = {
        "key": "x",
        "model": "auto",
        "persona": "",
        "style": "",
        "base_url": "https://custom.example.com/",
    }

    def mock_response(self) -> None:
        respx.get("https://custom.example.com/models").mock(
            httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "gpt-3.5-turbo",
                            "object": "model",
                            "created": 1686935002,
                            "owned_by": "openai",
                        }
                    ],
                },
            )
        )
        respx.post(
            "https://custom.example.com/chat/completions",
        ).mock(
            httpx.Response(
                200,
                json={
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "created": 1677652288,
                    "model": "gpt-3.5-turbo",
                    "system_fingerprint": "fp_44709d6fcb",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Ahoj světe",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 9,
                        "completion_tokens": 12,
                        "total_tokens": 21,
                    },
                },
            )
        )

    @responses.activate
    @respx.mock
    def test_clean_custom(self) -> None:
        self.mock_response()
        settings = self.CONFIGURATION.copy()
        machine = self.MACHINE_CLS
        form = self.MACHINE_CLS.settings_form(machine, settings)
        self.assertTrue(form.is_valid())

        settings["model"] = "custom"
        form = self.MACHINE_CLS.settings_form(machine, settings)
        self.assertFalse(form.is_valid())

        settings["custom_model"] = "custom"
        form = self.MACHINE_CLS.settings_form(machine, settings)
        self.assertTrue(form.is_valid())

        settings["model"] = "auto"
        form = self.MACHINE_CLS.settings_form(machine, settings)
        self.assertFalse(form.is_valid())


class AzureOpenAITranslationTest(OpenAITranslationTest):
    MACHINE_CLS: type[BatchMachineTranslation] = AzureOpenAITranslation
    CONFIGURATION = {
        "key": "x",
        "deployment": "my-deployment",
        "persona": "",
        "style": "",
        "azure_endpoint": "https://my-instance.openai.azure.com",
    }

    def mock_response(self) -> None:
        respx.post(
            "https://my-instance.openai.azure.com/openai/deployments/my-deployment/chat/completions?api-version=2024-06-01",
        ).mock(
            httpx.Response(
                200,
                json={
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "created": 1677652288,
                    "model": "my-deployment",
                    "system_fingerprint": "fp_44709d6fcb",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Ahoj světe",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 9,
                        "completion_tokens": 12,
                        "total_tokens": 21,
                    },
                },
            )
        )


class WeblateTranslationTest(TransactionsTestMixin, FixtureTestCase):
    def test_empty(self) -> None:
        machine = WeblateTranslation({})
        results = machine.translate(self.get_unit(), self.user)
        self.assertEqual(results, [[]])

    def test_exists(self) -> None:
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


class CyrTranslitTranslationTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base()

    def get_machine(self):
        return CyrTranslitTranslation({})

    def test_notsupported(self) -> None:
        machine = self.get_machine()

        # check empty result when source or translation language isn't supported
        unit = self.get_unit("Hello, world!\n")
        results = machine.translate(unit, self.user)
        self.assertEqual(results, [])

    def test_notsource(self) -> None:
        machine = self.get_machine()

        # check empty result when source and translation aren't from same language
        self.component.add_new_language(Language.objects.get(code="cnr_Cyrl"), None)
        unit = self.get_unit("Hello, world!\n", language="cnr_Cyrl")
        results = machine.translate(unit, self.user)
        self.assertEqual(results, [])

    def test_fallback_language(self):
        machine = self.get_machine()

        # Add translations and prepare units
        self.component.add_new_language(Language.objects.get(code="sr_Latn"), None)
        self.component.add_new_language(Language.objects.get(code="sr_Cyrl"), None)
        self.edit_unit("Hello, world!\n", "Moj hoverkraft je pun jegulja", "sr_Latn")
        latn_unit = self.get_unit("Hello, world!\n", language="sr_Latn")
        self.assertNotEqual(latn_unit.target, "")
        cyrl_unit = self.get_unit("Hello, world!\n", language="sr_Cyrl")
        self.assertEqual(cyrl_unit.target, "")

        # check latin to cyrillic
        results = machine.translate(cyrl_unit, self.user)
        self.assertEqual(
            results,
            [
                [
                    {
                        "text": "Мој ховеркрафт је пун јегуља\n",
                        "quality": 100,
                        "service": "CyrTranslit",
                        "source": "Moj hoverkraft je pun jegulja\n",
                        "original_source": "Moj hoverkraft je pun jegulja\n",
                    }
                ]
            ],
        )

        # Test not matching translation
        results = machine.translate(latn_unit, self.user)
        self.assertEqual(
            results,
            [],
        )

        # check cyrillic to latin
        self.edit_unit("Hello, world!\n", "Мој ховеркрафт је пун јегуља\n", "sr_Cyrl")
        results = machine.translate(latn_unit, self.user)
        self.assertEqual(results[0][0]["text"], "Moj hoverkraft je pun jegulja\n")

        # Force using source language only
        machine = CyrTranslitTranslation(
            {"source_language": SourceLanguageChoices.SOURCE}
        )
        results = machine.translate(latn_unit, self.user)
        self.assertEqual(results, [])

        # Secondary language source
        machine = CyrTranslitTranslation(
            {"source_language": SourceLanguageChoices.SECONDARY}
        )

        # None secondary language falls back to auto
        results = machine.translate(latn_unit, self.user)
        self.assertEqual(results[0][0]["text"], "Moj hoverkraft je pun jegulja\n")

        cyrillic_lang = Language.objects.get(code="sr_Cyrl")
        latin_lang = Language.objects.get(code="sr_Latn")

        # Not matching source language
        self.project.secondary_language = latin_lang
        self.project.save(update_fields=["secondary_language"])
        results = machine.translate(latn_unit, self.user)
        self.assertEqual(results, [])

        # Matching source language
        self.project.secondary_language = cyrillic_lang
        self.project.save(update_fields=["secondary_language"])
        results = machine.translate(latn_unit, self.user)
        self.assertEqual(results[0][0]["text"], "Moj hoverkraft je pun jegulja\n")

        # Component secondary overrides project
        self.component.secondary_language = latin_lang
        self.component.save(update_fields=["secondary_language"])
        results = machine.translate(latn_unit, self.user)
        self.assertEqual(results, [])

        self.component.secondary_language = cyrillic_lang
        self.component.save(update_fields=["secondary_language"])
        results = machine.translate(latn_unit, self.user)
        self.assertEqual(results[0][0]["text"], "Moj hoverkraft je pun jegulja\n")

    def test_multiple_languages(self):
        machine = self.get_machine()

        # Add translations and prepare units
        self.component.add_new_language(Language.objects.get(code="sr_Cyrl"), None)
        self.component.add_new_language(Language.objects.get(code="sr@ijekavian"), None)
        self.component.add_new_language(
            Language.objects.get(code="sr@ijekavian_Latn"), None
        )
        self.edit_unit(
            "Hello, world!\n", "Мој ховеркрафт је пун јегуља\n", "sr@ijekavian"
        )
        self.edit_unit("Hello, world!\n", "Мој ховеркрафт је пун\n", "sr_Cyrl")

        unit = self.get_unit("Hello, world!\n", language="sr@ijekavian_Latn")
        results = machine.translate(unit, self.user)
        self.assertEqual(
            results,
            [
                [
                    {
                        "text": "Moj hoverkraft je pun jegulja\n",
                        "quality": 100,
                        "service": "CyrTranslit",
                        "source": "Мој ховеркрафт је пун јегуља\n",
                        "original_source": "Мој ховеркрафт је пун јегуља\n",
                    }
                ]
            ],
        )

    def test_placeholders(self):
        machine = self.get_machine()

        # Add translations and prepare units
        self.component.add_new_language(Language.objects.get(code="sr_Latn"), None)
        self.component.add_new_language(Language.objects.get(code="sr_Cyrl"), None)
        self.edit_unit(
            "Orangutan has %d banana.\n", "Орангутан има %d банану.\n", "sr_Cyrl"
        )

        unit = self.get_unit("Orangutan has %d banana.\n", language="sr_Latn")

        # check cyrillic to latin
        results = machine.translate(unit, self.user)
        self.assertEqual(
            [
                [
                    {
                        "original_source": "Орангутан има %d банану.\n",
                        "quality": 100,
                        "service": "CyrTranslit",
                        "source": "Орангутан има %d банану.\n",
                        "text": "Orangutan ima %d bananu.\n",
                    }
                ],
                [],
                [],
            ],
            results,
        )


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
            category=SettingCategory.MT, name=service.get_identifier(), value={}
        )
        return service

    def test_translate(self) -> None:
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
                    "plural_form": 0,
                    "service": "Dummy",
                    "text": "Nazdar světe!",
                    "original_source": "Hello, world!\n",
                    "source": "Hello, world!\n",
                    "diff": "<ins>Nazdar světe!</ins>",
                    "source_diff": 'Hello, world!<span class="hlspace"><span class="space-nl">\n</span></span><br>',
                    "html": "Nazdar světe!",
                },
                {
                    "quality": 100,
                    "plural_form": 0,
                    "service": "Dummy",
                    "text": "Ahoj světe!",
                    "source": "Hello, world!\n",
                    "original_source": "Hello, world!\n",
                    "diff": "<ins>Ahoj světe!</ins>",
                    "source_diff": 'Hello, world!<span class="hlspace"><span class="space-nl">\n</span></span><br>',
                    "html": "Ahoj světe!",
                },
            ],
        )

        # Invalid service
        response = self.client.post(
            reverse("js-translate", kwargs={"unit_id": unit.id, "service": "invalid"})
        )
        self.assertEqual(response.status_code, 404)

    def test_memory(self) -> None:
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

    def test_configure_global(self) -> None:
        service = self.ensure_dummy_mt()
        list_url = reverse("manage-machinery")
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
                category=SettingCategory.MT, name=service.get_identifier()
            ).exists()
        )
        self.client.post(edit_url, {"install": "1"})
        self.assertTrue(
            Setting.objects.filter(
                category=SettingCategory.MT, name=service.get_identifier()
            ).exists()
        )

    def test_configure_project(self) -> None:
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
                category=SettingCategory.MT, name=service.get_identifier()
            ).exists()
        )
        project = Project.objects.get(pk=self.project.id)
        self.assertEqual(project.machinery_settings["dummy"], None)
        self.client.post(edit_url, {"enable": "1"})
        self.assertTrue(
            Setting.objects.filter(
                category=SettingCategory.MT, name=service.get_identifier()
            ).exists()
        )
        project = Project.objects.get(pk=self.component.project_id)
        self.assertNotIn("dummy", project.machinery_settings)

    def test_configure_invalid(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        identifier = "nonexisting"
        Setting.objects.create(category=SettingCategory.MT, name=identifier, value={})
        list_url = reverse("manage-machinery")
        edit_url = reverse("machinery-edit", kwargs={"machinery": identifier})
        response = self.client.get(list_url)
        self.assertContains(response, edit_url)

        self.client.post(edit_url, {"delete": "1"})
        self.assertFalse(
            Setting.objects.filter(
                category=SettingCategory.MT, name=identifier
            ).exists()
        )
        response = self.client.post(edit_url, {"install": "1"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            Setting.objects.filter(
                category=SettingCategory.MT, name=identifier
            ).exists()
        )


class CommandTest(FixtureTestCase):
    """Test for management commands."""

    def test_list_addons(self) -> None:
        output = StringIO()
        call_command("list_machinery", stdout=output)
        self.assertIn("DeepL", output.getvalue())

    def test_valid_install_no_form(self) -> None:
        output = StringIO()
        call_command(
            "install_machinery",
            "--service",
            "weblate",
            stdout=output,
            stderr=output,
        )
        self.assertIn("Service installed: Weblate", output.getvalue())

    def test_install_unknown_service(self) -> None:
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "install_machinery",
                "--service",
                "unknown",
                stdout=output,
                stderr=output,
            )

    def test_install_missing_form(self) -> None:
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "install_machinery",
                "--service",
                "deepl",
                stdout=output,
                stderr=output,
            )

    def test_install_wrong_form(self) -> None:
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "install_machinery",
                "--service",
                "deepl",
                "--configuration",
                '{"wrong": ""}',
                stdout=output,
                stderr=output,
            )

    @responses.activate
    def test_install_valid_form(self) -> None:
        output = StringIO()
        DeepLTranslationTest.mock_response()
        call_command(
            "install_machinery",
            "--service",
            "deepl",
            "--configuration",
            '{"key": "x1", "url": "https://api.deepl.com/v2/"}',
            stdout=output,
            stderr=output,
        )
        self.assertTrue(
            Setting.objects.filter(category=SettingCategory.MT, name="deepl").exists()
        )

        # update configuration
        call_command(
            "install_machinery",
            "--service",
            "deepl",
            "--configuration",
            '{"key": "x2", "url": "https://api.deepl.com/v2/"}',
            "--update",
            stdout=output,
            stderr=output,
        )

        setting = Setting.objects.get(category=SettingCategory.MT, name="deepl")
        self.assertEqual(
            setting.value, {"key": "x2", "url": "https://api.deepl.com/v2/"}
        )


class SourceLanguageTranslateTestCase(FixtureTestCase):
    LANGUAGE = "de"
    SOURCE = "Hello, world!\n"
    TRANSLATION = "Hallo, Welt!\n"

    def prepare(self) -> Unit:
        # Set German translation
        self.edit_unit(self.SOURCE, self.TRANSLATION, language=self.LANGUAGE)
        return self.get_unit(self.SOURCE)

    def test_translate(self):
        czech_unit = self.prepare()
        machine = DummyTranslation({})
        translation = machine.translate(
            czech_unit, source_language=Language.objects.get(code=self.LANGUAGE)
        )
        self.assertEqual(
            translation,
            [
                [
                    {
                        "text": "Ahoj německý světe!",
                        "quality": 100,
                        "service": "Dummy",
                        "source": "Hallo, Welt!\n",
                        "original_source": "Hallo, Welt!\n",
                    }
                ]
            ],
        )

    def test_batch_translate(self):
        czech_unit = self.prepare()
        machine = DummyTranslation({})
        machine.batch_translate(
            [czech_unit], source_language=Language.objects.get(code=self.LANGUAGE)
        )
        self.assertEqual(
            czech_unit.machinery,
            {
                "translation": ["Ahoj německý světe!"],
                "origin": [machine],
                "quality": [100],
            },
        )
