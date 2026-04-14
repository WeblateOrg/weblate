# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import re
from copy import copy
from datetime import UTC, datetime
from functools import partial
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NoReturn
from unittest.mock import MagicMock, Mock, call, patch

import httpx
import responses
import respx
from aliyunsdkcore.client import AcsClient
from botocore.stub import ANY, Stubber
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from google.api_core import exceptions as google_api_exceptions
from google.cloud.translate import (
    SupportedLanguages,
    TranslateTextResponse,
    TranslationServiceClient,
)
from google.cloud.translate_v3 import Glossary
from google.oauth2 import service_account
from requests.exceptions import HTTPError, JSONDecodeError

import weblate.machinery.models
from weblate.checks.tests.test_checks import MockUnit
from weblate.configuration.models import Setting, SettingCategory
from weblate.glossary.models import render_glossary_units_tsv
from weblate.lang.models import Language
from weblate.machinery.alibaba import AlibabaTranslation
from weblate.machinery.anthropic import AnthropicTranslation
from weblate.machinery.apertium import ApertiumAPYTranslation
from weblate.machinery.aws import AWSTranslation
from weblate.machinery.baidu import BAIDU_API, BaiduTranslation
from weblate.machinery.base import (
    MachineryRateLimitError,
    MachineTranslationError,
)
from weblate.machinery.cyrtranslit import CyrTranslitTranslation
from weblate.machinery.deepl import DeepLTranslation
from weblate.machinery.dummy import DummyGlossaryTranslation, DummyTranslation
from weblate.machinery.glosbe import GlosbeTranslation
from weblate.machinery.google import GOOGLE_API_ROOT, GoogleTranslation
from weblate.machinery.googlev3 import GoogleV3Translation
from weblate.machinery.libretranslate import LibreTranslateTranslation
from weblate.machinery.microsoft import MicrosoftCognitiveTranslation
from weblate.machinery.modernmt import ModernMTTranslation
from weblate.machinery.mymemory import MyMemoryTranslation
from weblate.machinery.netease import NETEASE_API_ROOT, NeteaseSightTranslation
from weblate.machinery.ollama import OllamaTranslation
from weblate.machinery.openai import AzureOpenAITranslation, OpenAITranslation
from weblate.machinery.saptranslationhub import SAPTranslationHub
from weblate.machinery.systran import SystranTranslation
from weblate.machinery.tmserver import TMServerTranslation
from weblate.machinery.weblatetm import WeblateTranslation
from weblate.machinery.yandex import YandexTranslation
from weblate.machinery.yandexv2 import YandexV2Translation
from weblate.machinery.youdao import YoudaoTranslation
from weblate.trans.models import Project, Unit
from weblate.trans.tests.test_views import (
    FixtureComponentTestCase,
    FixtureTestCase,
    ViewTestCase,
)
from weblate.trans.tests.utils import get_test_file
from weblate.utils.classloader import load_class
from weblate.utils.state import STATE_TRANSLATED

from .types import SourceLanguageChoices

if TYPE_CHECKING:
    from requests import PreparedRequest

    from weblate.machinery.base import (
        BatchMachineTranslation,
        SettingsDict,
    )

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

GOOGLEV3_KEY = Path(get_test_file("googlev3.json")).read_text(encoding="utf-8")

MODERNMT_RESPONSE = {
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
DEEPL_SOURCE_LANG_RESPONSE = [
    {"language": "EN", "name": "English"},
    {"language": "DE", "name": "Deutsch", "supports_formality": True},
    {"language": "PT", "name": "Portuguese"},
]
DEEPL_TARGET_LANG_RESPONSE = [
    {"language": "EN-GB", "name": "English (British)"},
    {"language": "DE", "name": "Deutsch", "supports_formality": True},
    {"language": "PT-BR", "name": "Portuguese (Brasilian)"},
    {"language": "PT-PT", "name": "Portuguese (European)", "supports_formality": True},
]

LIBRETRANSLATE_TRANS_RESPONSE = {"translatedText": "¡Hola, Mundo!"}
LIBRETRANSLATE_TRANS_ERROR_RESPONSE = {
    "error": "Please contact the server operator to obtain an API key"
}
LIBRETRANSLATE_LANG_RESPONSE = [
    {"code": "en", "name": "English"},
    {"code": "ar", "name": "Arabic"},
    {"code": "zh-Hant", "name": "Chinese (Traditional)"},
    {"code": "zh-Hans", "name": "Chinese (Simplified)"},
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
    CONFIGURATION: ClassVar[SettingsDict] = {}

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
        self,
        lang: str,
        word: str,
        expected_len: int,
        machine: BatchMachineTranslation | None = None,
        cache: bool = False,
        unit_args=None,
    ):
        if unit_args is None:
            unit_args = {}
        if machine is None:
            machine = self.get_machine(cache=cache)
        translation = machine.translate(MockUnit(code=lang, source=word, **unit_args))
        self.assertIsInstance(translation, list)
        if expected_len:
            self.assertGreater(len(translation), 0)
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

    def test_placeholders_backslash(self) -> None:
        machine_translation = self.get_machine()
        unit = MockUnit(code="cs", source=r"Hello, %s C:\Windows!", flags="c-format")
        self.assertEqual(
            machine_translation.cleanup_text(unit.source, unit),
            (r"Hello, [X7X] C:\Windows!", {"[X7X]": "%s"}),
        )
        self.assertEqual(
            machine_translation.translate(unit),
            [
                [
                    {
                        "quality": 100,
                        "service": "Dummy",
                        "source": r"Hello, %s C:\Windows!",
                        "original_source": r"Hello, %s C:\Windows!",
                        "text": r"Nazdar %s C:\Windows!",
                    }
                ]
            ],
        )

    def test_batch(self, machine=None) -> None:
        if machine is None:
            machine = self.get_machine()
        units = [
            MockUnit(code="cs", source="Hello, %s!", flags="c-format"),
            MockUnit(code="cs", source="Hello, %d!", flags="c-format"),
        ]
        machine.batch_translate(units)
        self.assertEqual(units[0].machinery["translation"], ["Nazdar %s!"])
        self.assertEqual(units[1].machinery["translation"], ["Nazdar %d!"])

    def test_key(self) -> None:
        machine_translation = self.get_machine()
        self.assertEqual(
            machine_translation.get_cache_key("test"),
            "mt:dummy:test:11364700946005001116",
        )


class MachineTranslationCleanupTest(SimpleTestCase):
    def test_rst_reference_remains_placeholder(self) -> None:
        machine_translation = DummyTranslation({})
        unit = MockUnit(
            code="cs", source=r"Hello, :ref:`docker-volume`!", flags="rst-text"
        )
        self.assertEqual(
            machine_translation.cleanup_text(unit.source, unit),
            ("Hello, [X7X]!", {"[X7X]": r":ref:`docker-volume`"}),
        )
        self.assertEqual(
            machine_translation.translate(unit),
            [
                [
                    {
                        "quality": 100,
                        "service": "Dummy",
                        "source": r"Hello, :ref:`docker-volume`!",
                        "original_source": r"Hello, :ref:`docker-volume`!",
                        "text": r"Nazdar :ref:`docker-volume`!",
                    }
                ]
            ],
        )

    def test_rst_suffix_reference_remains_placeholder(self) -> None:
        machine_translation = DummyTranslation({})
        unit = MockUnit(
            code="cs", source=r"Hello, `docker-volume`:ref:!", flags="rst-text"
        )
        self.assertEqual(
            machine_translation.cleanup_text(unit.source, unit),
            ("Hello, [X7X]!", {"[X7X]": r"`docker-volume`:ref:"}),
        )

    def test_rst_file_role_roundtrip(self) -> None:
        machine_translation = DummyTranslation({})
        unit = MockUnit(
            code="cs",
            source=r"Hello, :file:`C:\Windows\System.exe`!",
            flags="rst-text",
        )
        replaced, replacements = machine_translation.cleanup_text(unit.source, unit)
        self.assertEqual(
            (replaced, replacements),
            (
                r"Hello, [X7X]C:\Windows\System.exe[X35X]!",
                {
                    "[X7X]": ":file:`",
                    "[X35X]": "`",
                },
            ),
        )
        self.assertEqual(
            machine_translation.uncleanup_text(
                replacements,
                r"Ahoj, [X7X]C:\Windows\System.exe[X35X]!",
            ),
            r"Ahoj, :file:`C:\Windows\System.exe`!",
        )

    def test_rst_builtin_translatable_role_roundtrip(self) -> None:
        machine_translation = DummyTranslation({})
        unit = MockUnit(
            code="cs",
            source="Hello, :Code:`Save`!",
            flags="rst-text",
        )
        replaced, replacements = machine_translation.cleanup_text(unit.source, unit)
        self.assertEqual(
            (replaced, replacements),
            (
                "Hello, [X7X]Save[X18X]!",
                {
                    "[X7X]": ":Code:`",
                    "[X18X]": "`",
                },
            ),
        )
        self.assertEqual(
            machine_translation.uncleanup_text(
                replacements,
                "Ahoj, [X7X]Ulozit[X18X]!",
            ),
            "Ahoj, :Code:`Ulozit`!",
        )

    def test_rst_suffix_translatable_role_roundtrip(self) -> None:
        machine_translation = DummyTranslation({})
        unit = MockUnit(
            code="cs",
            source="Hello, `Save`:guilabel:!",
            flags="rst-text",
        )
        replaced, replacements = machine_translation.cleanup_text(unit.source, unit)
        self.assertEqual(
            (replaced, replacements),
            (
                "Hello, [X7X]Save[X12X]!",
                {
                    "[X7X]": "`",
                    "[X12X]": "`:guilabel:",
                },
            ),
        )
        self.assertEqual(
            machine_translation.uncleanup_text(
                replacements,
                "Ahoj, [X7X]Ulozit[X12X]!",
            ),
            "Ahoj, `Ulozit`:guilabel:!",
        )

    def test_rst_translatable_role_roundtrip(self) -> None:
        machine_translation = DummyTranslation({})
        unit = MockUnit(
            code="cs",
            source=(
                "Hello, :guilabel:`Sign out` and :ref:`review workflow <reviews>`!"
            ),
            flags="rst-text",
        )
        replaced, replacements = machine_translation.cleanup_text(unit.source, unit)
        self.assertEqual(
            (replaced, replacements),
            (
                "Hello, [X7X]Sign out[X26X] and [X32X]review workflow[X53X]!",
                {
                    "[X7X]": ":guilabel:`",
                    "[X26X]": "`",
                    "[X32X]": ":ref:`",
                    "[X53X]": " <reviews>`",
                },
            ),
        )
        self.assertEqual(
            machine_translation.uncleanup_text(
                replacements,
                "Ahoj, [X7X]Odhlásit se[X26X] a [X32X]pracovní postup kontroly[X53X]!",
            ),
            "Ahoj, :guilabel:`Odhlásit se` a :ref:`pracovní postup kontroly <reviews>`!",
        )

    def test_rst_role_duplicate_fragment_roundtrip(self) -> None:
        machine_translation = DummyTranslation({})
        unit = MockUnit(
            code="cs",
            source="Use ``:ref:`foo``` syntax, then see :ref:`foo`.",
            flags="rst-text",
        )
        replaced, replacements = machine_translation.cleanup_text(unit.source, unit)
        self.assertEqual(
            (replaced, replacements),
            (
                "Use ``:ref:`foo``` syntax, then see [X36X].",
                {"[X36X]": ":ref:`foo`"},
            ),
        )

    def test_rst_escaped_role_example_roundtrip(self) -> None:
        machine_translation = DummyTranslation({})
        unit = MockUnit(
            code="cs",
            source=r"Use \:ref:`foo` literally, then see :ref:`foo`.",
            flags="rst-text",
        )
        replaced, replacements = machine_translation.cleanup_text(unit.source, unit)
        self.assertEqual(
            (replaced, replacements),
            (
                r"Use \:ref:`foo` literally, then see [X36X].",
                {"[X36X]": ":ref:`foo`"},
            ),
        )


class GlossaryTranslationTest(BaseMachineTranslationTest):
    """Test case for glossary translation functionality."""

    MACHINE_CLS = DummyGlossaryTranslation

    @patch("weblate.glossary.models.get_glossary_tsv", new=lambda _: "foo\tbar")
    # pylint: disable-next=arguments-differ
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
            self.assertGreater(len(result), 0)
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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

    @responses.activate
    def test_non_json_error_response_falls_back_to_http_error(self) -> None:
        responses.add(
            responses.GET,
            "https://mymemory.translated.net/api/get",
            body=(
                "<html><head><title>403 Forbidden</title></head><body>"
                "<center><h1>403 Forbidden</h1></center></body></html>"
            ),
            content_type="text/html",
            status=403,
        )

        with self.assertRaises(MachineTranslationError) as raised:
            self.assert_translate(self.SUPPORTED, self.SOURCE_BLANK, 0)

        self.assertIsInstance(raised.exception.__cause__, HTTPError)
        self.assertIn("403 Client Error", str(raised.exception))


class ApertiumAPYTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = ApertiumAPYTranslation
    ENGLISH = "eng"
    SUPPORTED = "spa"
    EXPECTED_LEN = 1
    CONFIGURATION: ClassVar[SettingsDict] = {
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
        call_2 = responses.calls[1]
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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

    @responses.activate
    def test_regional_host_string_payload_raises_error(self) -> None:
        machine = self.MACHINE_CLS(
            {
                **self.CONFIGURATION,
                "base_url": "api-eur.cognitive.microsofttranslator.com",
            }
        )
        responses.add(
            responses.POST,
            "https://westeurope.api.cognitive.microsoft.com/sts/v1.0/issueToken"
            "?Subscription-Key=KEY",
            body="TOKEN",
        )
        responses.add(
            responses.GET,
            "https://api-eur.cognitive.microsofttranslator.com/languages?api-version=3.0",
            json=MS_SUPPORTED_LANG_RESP,
        )
        responses.add(
            responses.POST,
            "https://api-eur.cognitive.microsofttranslator.com/"
            "translate?api-version=3.0&from=en&to=cs&category=general&textType=html",
            json="Regional host error",
        )

        with self.assertRaisesRegex(MachineTranslationError, "Regional host error"):
            self.assert_translate(self.SUPPORTED, self.SOURCE_BLANK, 0, machine=machine)


class GoogleTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = GoogleTranslation
    EXPECTED_LEN = 1
    CONFIGURATION: ClassVar[SettingsDict] = {
        "key": "KEY",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(responses.GET, f"{GOOGLE_API_ROOT}languages", body="", status=500)
        responses.add(responses.GET, GOOGLE_API_ROOT, body="", status=500)

    def mock_response(self) -> None:
        responses.add(
            responses.GET,
            f"{GOOGLE_API_ROOT}languages",
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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
                    failed_message = "Blob file was not found"
                    raise google_api_exceptions.NotFound(failed_message)

        return MockBlob


class TMServerTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = TMServerTranslation
    EXPECTED_LEN = 1
    SOURCE_TRANSLATED = "Hello"
    CONFIGURATION: ClassVar[SettingsDict] = {
        "url": AMAGAMA_LIVE,
    }

    def mock_empty(self) -> None:
        responses.add(responses.GET, f"{AMAGAMA_LIVE}/languages/", body="", status=404)
        responses.add(responses.GET, f"{AMAGAMA_LIVE}/en/cs/unit/Hello", json=[])

    def mock_response(self) -> None:
        responses.add(
            responses.GET,
            f"{AMAGAMA_LIVE}/languages/",
            json={"sourceLanguages": ["en"], "targetLanguages": ["cs"]},
        )
        responses.add(
            responses.GET, f"{AMAGAMA_LIVE}/en/cs/unit/Hello", json=AMAGAMA_JSON
        )
        responses.add(
            responses.GET, f"{AMAGAMA_LIVE}/en/de/unit/test", json=AMAGAMA_JSON
        )

    def mock_error(self) -> None:
        responses.add(responses.GET, f"{AMAGAMA_LIVE}/languages/", body="", status=404)
        responses.add(
            responses.GET, f"{AMAGAMA_LIVE}/en/cs/unit/Hello", body="", status=500
        )


class YandexTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = YandexTranslation
    EXPECTED_LEN = 1
    CONFIGURATION: ClassVar[SettingsDict] = {
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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
    CONFIGURATION: ClassVar[SettingsDict] = {"key": "id", "secret": "secret"}

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
    CONFIGURATION: ClassVar[SettingsDict] = {
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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
    CONFIGURATION: ClassVar[SettingsDict] = {
        "key": "id",
        "username": "username",
        "password": "password",
        "url": "http://sth.example.com/",
        "enable_mt": False,
    }


class ModernMTTest(BaseMachineTranslationTest):
    MACHINE_CLS = ModernMTTranslation
    EXPECTED_LEN = 1
    ENGLISH = "en"
    SUPPORTED = "it"
    CONFIGURATION: ClassVar[SettingsDict] = {
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
            "https://api.modernmt.com/translate/languages",
            json={
                "data": ["en", "sr", "cs", "it", "ja"],
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
            json=MODERNMT_RESPONSE,
            status=200,
            content_type="text/json",
        )

        self.mock_list_glossaries()

    def mock_list_glossaries(self, *id_name_date: tuple[int, str, str | None]) -> None:
        """Set up mock responses for list of glossaries in ModernMT."""
        data: list[dict] = [
            {
                "id": glossary_id,
                "creationDate": glossary_date or "2021-04-12T15:24:26+00:00",
                "name": glossary_name,
            }
            for glossary_id, glossary_name, glossary_date in id_name_date
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
            return (200, {}, json.dumps(MODERNMT_RESPONSE))

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

    def test_glossary_with_delete_fail(self) -> None:
        self.test_glossary(fail_delete_glossary=True)

    @responses.activate
    def test_context_vector(self) -> None:
        """Test that context vector is sent with the request when configured."""

        def request_callback(request: PreparedRequest):
            """Check 'context_vector' included in request body."""
            self.assertIn("context_vector", request.params)
            return (200, {}, json.dumps(MODERNMT_RESPONSE))

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
    CONFIGURATION: ClassVar[SettingsDict] = {
        "key": "KEY",
        "url": "https://api.deepl.com/v2/",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.GET,
            "https://api.deepl.com/v2/languages",
            status=500,
        )
        responses.add(
            responses.POST,
            "https://api.deepl.com/v2/translate",
            status=500,
        )

    @staticmethod
    def mock_languages() -> None:
        responses.add(
            responses.GET,
            "https://api.deepl.com/v2/languages?type=source",
            json=DEEPL_SOURCE_LANG_RESPONSE,
        )
        responses.add(
            responses.GET,
            "https://api.deepl.com/v2/languages?type=target",
            json=DEEPL_TARGET_LANG_RESPONSE,
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
    # pylint: disable-next=arguments-differ
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
        self.assertEqual(len(responses.calls), 4)
        self.assertEqual(
            [(call.request.method, call.request.url) for call in responses.calls],
            [
                ("GET", "https://api.deepl.com/v2/languages?type=source"),
                ("GET", "https://api.deepl.com/v2/languages?type=target"),
                ("GET", "https://api.deepl.com/v2/glossary-language-pairs"),
                ("POST", "https://api.deepl.com/v2/translate"),
            ],
        )
        responses.reset()
        # Fetch from cache
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        self.assert_translate(
            self.SUPPORTED, self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assertEqual(len(responses.calls), 0)

    @responses.activate
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

    @responses.activate
    def test_languages_map(self) -> None:
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        self.mock_languages()
        lang_pt = Language.objects.get(code="pt")
        lang_pt_br = Language.objects.get(code="pt_BR")
        lang_pt_pt = Language.objects.get(code="pt_PT")
        lang_en = Language.objects.get(code="en")
        self.assertEqual(machine.get_languages(lang_pt_br, lang_en), ("PT", "EN"))
        self.assertEqual(machine.get_languages(lang_pt, lang_pt_br), ("PT", "PT-BR"))
        self.assertEqual(machine.get_languages(lang_en, lang_pt), ("EN", "PT-PT"))
        self.assertEqual(machine.get_languages(lang_en, lang_pt_pt), ("EN", "PT-PT"))


class LibreTranslateTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS = LibreTranslateTranslation
    EXPECTED_LEN = 1
    ENGLISH = "en"
    SUPPORTED = "es"
    NOTSUPPORTED = "cs"
    CONFIGURATION: ClassVar[SettingsDict] = {
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
    def test_chinese(self) -> None:
        machine = self.MACHINE_CLS(self.CONFIGURATION)
        machine.delete_cache()
        self.mock_response()
        self.assert_translate(
            "zh_Hant", self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
        )
        self.assert_translate(
            "zh_Hans", self.SOURCE_TRANSLATED, self.EXPECTED_LEN, machine=machine
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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

    def test_support(self, machine_translation=None) -> None:
        if machine_translation is None:
            machine_translation = self.get_machine()
        machine_translation.delete_cache()
        with Stubber(machine_translation.client) as stubber:
            stubber.add_response(
                "list_languages",
                AWS_LANGUAGES_RESPONSE,
            )
            super().test_support(machine_translation)

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
        self, machine: AWSTranslation, fail_delete: bool = True
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
    CONFIGURATION: ClassVar[SettingsDict] = {
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


class OpenAITranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS: type[BatchMachineTranslation] = OpenAITranslation
    EXPECTED_LEN = 1
    ENGLISH = "en"
    SUPPORTED = "zh-TW"
    NOTSUPPORTED = None
    CONFIGURATION: ClassVar[SettingsDict] = {
        "key": "x",
        "model": "auto",
        "persona": "",
        "style": "",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> NoReturn:
        self.skipTest("Not tested")

    @staticmethod
    def mock_models() -> None:
        respx.get("https://api.openai.com/v1/models").mock(
            httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "gpt-5-nano",
                            "object": "model",
                            "created": 1686935002,
                            "owned_by": "openai",
                        }
                    ],
                },
            )
        )

    def mock_response(self, content: str = '["Ahoj světe"]') -> None:
        self.mock_models()
        respx.post(
            "https://api.openai.com/v1/chat/completions",
        ).mock(
            httpx.Response(
                200,
                json={
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "created": 1677652288,
                    "model": "gpt-5-nano",
                    "system_fingerprint": "fp_44709d6fcb",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": content,
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
    def test_translate_repairs_invalid_json_string_quotes(self) -> None:
        source = "Synthetic source string for malformed JSON recovery."
        self.mock_response('["Préfixe "citation" suffixe"]')

        translation = self.assert_translate(
            "fr",
            source,
            1,
        )

        self.assertEqual(
            translation[0][0]["text"],
            'Préfixe "citation" suffixe',
        )

    @responses.activate
    @respx.mock
    def test_translate_uses_llm_placeholder_syntax(self) -> None:
        machine = self.get_machine()

        def request_callback(
            _prompt: str,
            content: str,
            previous_content: str,
            previous_response: str,
        ) -> str:
            self.assertIn("@@PH", content)
            self.assertNotIn("[X", content)

            placeholder = re.search(r"@@PH\d+@@", content)
            self.assertIsNotNone(placeholder)

            previous_payload = json.loads(previous_content)
            previous_sources = [item["source"] for item in previous_payload["strings"]]
            self.assertTrue(
                any(
                    '<a href="/x">log out</a>' in source and "@@PH195@@" in source
                    for source in previous_sources
                )
            )
            self.assertNotIn("[X", previous_content)

            previous_translations = json.loads(previous_response)
            self.assertTrue(
                any(
                    '<a href="/x">odhlásit se</a>' in translation
                    and "@@PH195@@" in translation
                    for translation in previous_translations
                )
            )

            return json.dumps([f"Bonjour {placeholder.group()}! <<foo>>"])

        with patch.object(
            machine, "fetch_llm_translations", side_effect=request_callback
        ):
            translation = self.assert_translate(
                "fr",
                "Hello, %s! <<foo>>",
                1,
                machine=machine,
                unit_args={"flags": "python-format"},
            )

        self.assertEqual(translation[0][0]["text"], "Bonjour %s! <<foo>>")

    @responses.activate
    @respx.mock
    def test_translate_repairs_escaped_placeholders(self) -> None:
        source = "List filtered by responses to custom field @@PH44@@."
        self.mock_response(
            '["Liste filtree selon les responses au champ personnalise \\@\\@PH44 \\@\\@."]'
        )

        translation = self.get_machine().download_multiple_translations(
            "en",
            "fr",
            [(source, None)],
        )

        self.assertEqual(
            translation[source][0]["text"],
            "Liste filtree selon les responses au champ personnalise @@PH44@@.",
        )

    @responses.activate
    @respx.mock
    def test_translate_placeholderizes_existing_translation(self) -> None:
        machine = self.get_machine()
        existing_translation = "Bonjour, %s! <<foo>>"

        def request_callback(
            _prompt: str,
            content: str,
            _previous_content: str,
            _previous_response: str,
        ) -> str:
            payload = json.loads(content)
            self.assertIn("@@PH", content)
            self.assertEqual(
                payload["strings"][0]["translation"],
                "Bonjour, @@PH7@@! <<foo>>",
            )
            return json.dumps(["Bonjour, @@PH7@@! <<foo>>"])

        with patch.object(
            machine, "fetch_llm_translations", side_effect=request_callback
        ):
            translation = self.assert_translate(
                "fr",
                "Hello, %s! <<foo>>",
                1,
                machine=machine,
                unit_args={"flags": "python-format", "target": existing_translation},
            )

        self.assertEqual(translation[0][0]["text"], existing_translation)

    def test_translate_recovers_plural_placeholder_source_variant(self) -> None:
        machine = self.get_machine()
        unit = MockUnit(
            code="fr",
            source=["Single item.", "Items: %d."],
            target=["Articles: %d.", "Articles: %d."],
            flags="python-format",
        )

        def request_callback(
            _prompt: str,
            content: str,
            _previous_content: str,
            _previous_response: str,
        ) -> str:
            payload = json.loads(content)
            self.assertEqual(
                payload["strings"][0]["translation"],
                "Articles: @@PH7@@.",
            )
            return json.dumps(["Articles: %d."])

        with patch.object(
            machine, "fetch_llm_translations", side_effect=request_callback
        ):
            translation = machine.download_multiple_translations(
                "en",
                "fr",
                [("Items: @@PH7@@.", unit)],
            )

        self.assertEqual(
            translation["Items: @@PH7@@."][0]["text"],
            "Articles: @@PH7@@.",
        )

    def test_translate_recovers_secondary_source_plural_placeholder_variant(
        self,
    ) -> None:
        machine = self.get_machine()
        unit = MockUnit(
            code="fr",
            source=["Single item.", "Items: %d."],
            target=["Articles: %d.", "Articles: %d."],
            flags="python-format",
        )
        unit.plural_map = ["Single mapped item.", "Mapped: %d."]

        def request_callback(
            _prompt: str,
            content: str,
            _previous_content: str,
            _previous_response: str,
        ) -> str:
            payload = json.loads(content)
            self.assertEqual(
                payload["strings"][0]["translation"],
                "Articles: @@PH8@@.",
            )
            return json.dumps(["Articles: %d."])

        with patch.object(
            machine, "fetch_llm_translations", side_effect=request_callback
        ):
            translation = machine.download_multiple_translations(
                "de",
                "fr",
                [("Mapped: @@PH8@@.", unit)],
            )

        self.assertEqual(
            translation["Mapped: @@PH8@@."][0]["text"],
            "Articles: @@PH8@@.",
        )

    @responses.activate
    @respx.mock
    def test_translate_omits_unmappable_existing_translation(self) -> None:
        machine = self.get_machine()
        broken_translation = "Bonjour tout le monde! <<foo>>"

        def request_callback(
            _prompt: str,
            content: str,
            _previous_content: str,
            _previous_response: str,
        ) -> str:
            payload = json.loads(content)
            self.assertNotIn("translation", payload["strings"][0])
            return json.dumps(["Bonjour @@PH7@@! <<foo>>"])

        with patch.object(
            machine, "fetch_llm_translations", side_effect=request_callback
        ):
            translation = self.assert_translate(
                "fr",
                "Hello, %s! <<foo>>",
                1,
                machine=machine,
                unit_args={"flags": "python-format", "target": broken_translation},
            )

        self.assertEqual(translation[0][0]["text"], "Bonjour %s! <<foo>>")

    @responses.activate
    @respx.mock
    def test_translate_maps_reordered_distinct_placeholders(self) -> None:
        machine = self.get_machine()

        def request_callback(
            _prompt: str,
            content: str,
            _previous_content: str,
            _previous_response: str,
        ) -> str:
            placeholders = re.findall(r"@@PH\d+@@", content)
            self.assertEqual(len(placeholders), 2)
            return json.dumps([f"Items: {placeholders[1]}, value: {placeholders[0]}."])

        with patch.object(
            machine, "fetch_llm_translations", side_effect=request_callback
        ):
            translation = self.assert_translate(
                "fr",
                "Value: %s, items: %d.",
                1,
                machine=machine,
                unit_args={"flags": "python-format"},
            )

        self.assertEqual(
            translation[0][0]["text"],
            "Items: %d, value: %s.",
        )

    @responses.activate
    @respx.mock
    def test_translate_rejects_unmappable_rst_markup(self) -> None:
        self.mock_response('["Voir :ref:`branche-cible`."]')

        with self.assertRaises(MachineTranslationError):
            self.assert_translate(
                "fr",
                "See :ref:`target-branch`.",
                1,
                unit_args={"flags": "rst-text"},
            )

    @responses.activate
    @respx.mock
    def test_translate_rejects_unmappable_single_highlight(self) -> None:
        self.mock_response('["Hello, `friend`!"]')

        with self.assertRaises(MachineTranslationError):
            self.assert_translate(
                "fr",
                "Hello, %s!",
                1,
                unit_args={"flags": "python-format"},
            )

    @responses.activate
    @respx.mock
    def test_translate_rejects_placeholder_mismatch(self) -> None:
        self.mock_response('["Synthetic source string without placeholder."]')

        with self.assertRaises(MachineTranslationError):
            self.get_machine().download_multiple_translations(
                "en",
                "fr",
                [("Synthetic source string with @@PH44@@ placeholder.", None)],
            )

    @responses.activate
    @respx.mock
    def test_translate_recovers_spaced_placeholder_syntax(self) -> None:
        self.mock_response('["Bonjour @@PH7@ @! <<foo>>"]')

        translation = self.assert_translate(
            "fr",
            "Hello, %s! <<foo>>",
            1,
            unit_args={"flags": "python-format"},
        )

        self.assertEqual(translation[0][0]["text"], "Bonjour %s! <<foo>>")

    @responses.activate
    @respx.mock
    def test_translate_restores_placeholder_before_literal_at(self) -> None:
        machine = self.get_machine()

        def request_callback(
            _prompt: str,
            content: str,
            _previous_content: str,
            _previous_response: str,
        ) -> str:
            placeholder = re.search(r"@@PH\d+@@", content)
            self.assertIsNotNone(placeholder)
            self.assertIn(f"{placeholder.group()}@example.com", content)
            return json.dumps([f"{placeholder.group()}@example.com"])

        with patch.object(
            machine, "fetch_llm_translations", side_effect=request_callback
        ):
            translation = self.assert_translate(
                "fr",
                "%s@example.com",
                1,
                machine=machine,
                unit_args={"flags": "python-format"},
            )

        self.assertEqual(translation[0][0]["text"], "%s@example.com")

    @responses.activate
    @respx.mock
    def test_translate_accepts_adjacent_placeholders(self) -> None:
        machine = self.get_machine()

        def request_callback(
            _prompt: str,
            content: str,
            _previous_content: str,
            _previous_response: str,
        ) -> str:
            placeholders = re.findall(r"@@PH\d+@@", content)
            self.assertEqual(len(placeholders), 2)
            return json.dumps([f"{placeholders[0]}{placeholders[1]}"])

        with patch.object(
            machine, "fetch_llm_translations", side_effect=request_callback
        ):
            translation = self.assert_translate(
                "fr",
                "%s%s",
                1,
                machine=machine,
                unit_args={"flags": "python-format"},
            )

        self.assertEqual(translation[0][0]["text"], "%s%s")

    @responses.activate
    @respx.mock
    def test_translate_rejects_placeholder_with_trailing_at(self) -> None:
        self.mock_response('["Bonjour @@PH7@@@! <<foo>>"]')

        with self.assertRaises(MachineTranslationError):
            self.assert_translate(
                "fr",
                "Hello, %s! <<foo>>",
                1,
                unit_args={"flags": "python-format"},
            )

    @responses.activate
    @respx.mock
    def test_translate_rejects_legacy_placeholder_syntax(self) -> None:
        self.mock_response('["Synthetic source string with [X44X] placeholder."]')

        with self.assertRaises(MachineTranslationError):
            self.get_machine().download_multiple_translations(
                "en",
                "fr",
                [("Synthetic source string with @@PH44@@ placeholder.", None)],
            )

    @responses.activate
    @respx.mock
    def test_translate_rejects_missing_comma_between_items(self) -> None:
        self.mock_response('["Premier" "Deuxieme", "Troisieme"]')

        with self.assertRaises(MachineTranslationError):
            self.get_machine().download_multiple_translations(
                "en",
                "fr",
                [("One", None), ("Two", None)],
            )

    @responses.activate
    @respx.mock
    def test_translate_blank_reply_reports_single_exception_event(self) -> None:
        machine = self.get_machine()
        handled_cause = f"machinery[{machine.name}]: Blank assistant reply"
        report_cause = f"machinery[{machine.name}]: Could not fetch translations"

        with (
            patch("weblate.machinery.base.log_handled_exception") as mock_log_handled,
            patch("weblate.machinery.base.report_error") as mock_report_error,
            patch.object(machine, "fetch_llm_translations", return_value=""),
            self.assertRaises(MachineTranslationError),
        ):
            self.assert_translate("fr", "Hello", 1, machine=machine)

        mock_log_handled.assert_called_once_with(handled_cause, extra_log="")
        mock_report_error.assert_called_once_with(
            report_cause, extra_log=None, message=False
        )

    @responses.activate
    @respx.mock
    def test_translate_parse_error_reports_single_exception_event(self) -> None:
        machine = self.get_machine()
        handled_cause = (
            f"machinery[{machine.name}]: Could not parse assistant reply as JSON."
        )
        report_cause = f"machinery[{machine.name}]: Could not fetch translations"

        with (
            patch("weblate.machinery.base.log_handled_exception") as mock_log_handled,
            patch("weblate.machinery.base.report_error") as mock_report_error,
            patch.object(
                machine, "fetch_llm_translations", return_value='["Ahoj "svete"]'
            ),
            patch.object(machine, "_repair_json_string_array", return_value=None),
            self.assertRaises(MachineTranslationError),
        ):
            self.assert_translate("fr", "Hello", 1, machine=machine)

        mock_log_handled.assert_called_once_with(
            handled_cause,
            extra_log='["Ahoj "svete"]',
        )
        mock_report_error.assert_called_once_with(
            report_cause, extra_log=None, message=False
        )

    @responses.activate
    @respx.mock
    def test_translate_still_rejects_unrepairable_json(self) -> None:
        self.mock_response('["Ahoj světe"')

        with self.assertRaises(MachineTranslationError):
            self.assert_translate(self.SUPPORTED, self.SOURCE_TRANSLATED, 1)

    @responses.activate
    @respx.mock
    def test_translate_chains_repaired_json_decode_error(self) -> None:
        self.mock_response('["Ahoj "svete"]')

        with (
            patch.object(
                self.MACHINE_CLS,
                "_repair_json_string_array",
                return_value='["unterminated]',
            ),
            self.assertRaises(MachineTranslationError) as error,
        ):
            self.assert_translate(self.SUPPORTED, self.SOURCE_TRANSLATED, 1)

        self.assertIsInstance(error.exception.__cause__, json.JSONDecodeError)
        self.assertIn(
            "Unterminated string",
            str(error.exception.__cause__),
        )


class OpenAICustomTranslationTest(OpenAITranslationTest):
    CONFIGURATION: ClassVar[SettingsDict] = {
        "key": "x",
        "model": "auto",
        "persona": "",
        "style": "",
        "base_url": "https://custom.example.com/",
    }

    def mock_response(self, content: str = '["Ahoj světe"]') -> None:
        respx.get("https://custom.example.com/models").mock(
            httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "gpt-5-nano",
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
                    "model": "gpt-5-nano",
                    "system_fingerprint": "fp_44709d6fcb",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": content,
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
        form = machine.settings_form(machine, settings)
        self.assertTrue(form.is_valid())

        settings["model"] = "custom"
        form = machine.settings_form(machine, settings)
        self.assertFalse(form.is_valid())

        settings["custom_model"] = "custom"
        form = machine.settings_form(machine, settings)
        self.assertTrue(form.is_valid())

        settings["model"] = "auto"
        form = machine.settings_form(machine, settings)
        self.assertFalse(form.is_valid())

    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_runtime_url_validation(self, mocked_getaddrinfo) -> None:
        machine = self.MACHINE_CLS(self.CONFIGURATION.copy())
        machine.delete_cache()
        machine.settings["_project"] = Mock()

        with (
            patch.object(machine.client.models, "list") as mocked_list,
            self.assertRaises(ValidationError),
        ):
            machine.get_model()

        mocked_getaddrinfo.assert_called_once()
        mocked_list.assert_not_called()

    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=OSError("Name or service not known"),
    )
    def test_runtime_url_validation_uses_proxy_settings(
        self, mocked_getaddrinfo
    ) -> None:
        machine = self.MACHINE_CLS(self.CONFIGURATION.copy())
        machine.delete_cache()
        machine.settings["_project"] = Mock()

        with (
            patch.dict(
                os.environ,
                {
                    "HTTPS_PROXY": "http://127.0.0.1:8080",
                    "HTTP_PROXY": "",
                    "ALL_PROXY": "",
                    "NO_PROXY": "",
                },
            ),
            patch.object(
                machine.client.models,
                "list",
                return_value=[Mock(id="gpt-5-nano")],
            ) as mocked_list,
        ):
            self.assertEqual(machine.get_model(), "gpt-5-nano")

        mocked_getaddrinfo.assert_not_called()
        mocked_list.assert_called_once()


class AzureOpenAITranslationTest(OpenAITranslationTest):
    MACHINE_CLS: type[BatchMachineTranslation] = AzureOpenAITranslation
    CONFIGURATION: ClassVar[SettingsDict] = {
        "key": "x",
        "deployment": "my-deployment",
        "persona": "",
        "style": "",
        "azure_endpoint": "https://my-instance.openai.azure.com",
    }

    def mock_response(self, content: str = '["Ahoj světe"]') -> None:
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
                                "content": content,
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

    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=OSError("Name or service not known"),
    )
    def test_runtime_url_validation_uses_proxy_settings(
        self, mocked_getaddrinfo
    ) -> None:
        machine = self.MACHINE_CLS(self.CONFIGURATION.copy())
        machine.settings["_project"] = Mock()
        completion = Mock()
        completion.choices = [Mock(message=Mock(content='["Ahoj světe"]'))]

        with (
            patch.dict(
                os.environ,
                {
                    "HTTPS_PROXY": "http://127.0.0.1:8080",
                    "HTTP_PROXY": "",
                    "ALL_PROXY": "",
                    "NO_PROXY": "",
                },
            ),
            patch.object(
                machine.client.chat.completions,
                "create",
                return_value=completion,
            ) as mocked_create,
        ):
            self.assertEqual(
                machine.fetch_llm_translations("prompt", "content", "prev", "resp"),
                '["Ahoj světe"]',
            )

        mocked_getaddrinfo.assert_not_called()
        mocked_create.assert_called_once()


class OllamaTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS: type[BatchMachineTranslation] = OllamaTranslation
    EXPECTED_LEN = 1
    ENGLISH = "en"
    SUPPORTED = "eu"
    NOTSUPPORTED = None
    CONFIGURATION: ClassVar[SettingsDict] = {
        "base_url": "http://localhost:11434",
        "model": "itzune/latxa:8b",
        "persona": "You are a squirrel breeder",
        "style": "",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.POST,
            "http://localhost:11434/api/chat",
            status=404,
            json={"error": "the model failed to generate a response"},
        )

    def mock_response(self) -> None:
        responses.add(
            responses.POST,
            "http://localhost:11434/api/chat",
            status=200,
            json={
                "model": "itzune/latxa:8b",
                "created_at": "2025-11-29T21:25:08.441817763Z",
                "message": {
                    "role": "assistant",
                    "content": '["Sakatu SUTAN jarraitzeko"]',
                },
                "done": True,
                "done_reason": "stop",
                "total_duration": 3946971317,
                "load_duration": 3325185239,
                "prompt_eval_count": 73,
                "prompt_eval_duration": 107465065,
                "eval_count": 11,
                "eval_duration": 503286987,
            },
        )


class OllamaRemoteModelTranslationTest(OllamaTranslationTest):
    CONFIGURATION: ClassVar[SettingsDict] = {
        "base_url": "http://localhost:11434",
        "model": "minimax-m2:cloud",
        "persona": "",
        "style": "",
    }

    def mock_response(self) -> None:
        responses.add(
            responses.POST,
            "http://localhost:11434/api/chat",
            status=200,
            json={
                "model": "minimax-m2:cloud",
                "remote_model": "minimax-m2",
                "remote_host": "https://ollama.com:443",
                "created_at": "2025-11-29T21:43:24.529609868Z",
                "message": {
                    "role": "assistant",
                    "content": '["Sakatu FIRE tekla jarraitzeko."]',
                },
                "done": True,
                "done_reason": "stop",
                "total_duration": 5740856828,
                "prompt_eval_count": 63,
                "eval_count": 481,
            },
        )


class AnthropicTranslationTest(BaseMachineTranslationTest):
    MACHINE_CLS: type[BatchMachineTranslation] = AnthropicTranslation
    EXPECTED_LEN = 1
    ENGLISH = "en"
    SUPPORTED = "de"
    NOTSUPPORTED = None
    CONFIGURATION: ClassVar[SettingsDict] = {
        "key": "test-api-key",
        "base_url": "https://api.anthropic.com",
        "model": "claude-sonnet-4-5",
        "max_tokens": 4096,
        "persona": "",
        "style": "",
    }

    def mock_empty(self) -> NoReturn:
        self.skipTest("Not tested")

    def mock_error(self) -> None:
        responses.add(
            responses.POST,
            "https://api.anthropic.com/v1/messages",
            status=400,
            json={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Invalid API key provided",
                },
            },
        )

    def mock_response(self) -> None:
        responses.add(
            responses.POST,
            "https://api.anthropic.com/v1/messages",
            status=200,
            json={
                "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": '["Hallo Welt"]',
                    }
                ],
                "model": "claude-sonnet-4-5",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 25,
                    "output_tokens": 5,
                },
            },
        )

    @responses.activate
    def test_empty_base_url_uses_default(self) -> None:
        responses.add(
            responses.POST,
            "https://api.anthropic.com/v1/messages",
            status=200,
            json={
                "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": '["Hallo Welt"]',
                    }
                ],
                "model": "claude-sonnet-4-5",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 25,
                    "output_tokens": 5,
                },
            },
        )

        machine = self.MACHINE_CLS({**self.CONFIGURATION, "base_url": ""})
        self.assert_translate(
            self.SUPPORTED,
            self.SOURCE_BLANK,
            self.EXPECTED_LEN,
            machine=machine,
        )

    @responses.activate
    def test_error_non_json(self) -> None:
        responses.add(
            responses.POST,
            "https://api.anthropic.com/v1/messages",
            status=200,
            json={
                "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "Hallo Welt",
                    }
                ],
                "model": "claude-sonnet-4-5",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 25,
                    "output_tokens": 5,
                },
            },
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(self.SUPPORTED, self.SOURCE_BLANK, 0)

    @responses.activate
    def test_error_wrong_type(self) -> None:
        responses.add(
            responses.POST,
            "https://api.anthropic.com/v1/messages",
            status=200,
            json={
                "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": '{"translation": "Hallo Welt"}',
                    }
                ],
                "model": "claude-sonnet-4-5",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 25,
                    "output_tokens": 5,
                },
            },
        )
        with self.assertRaises(MachineTranslationError):
            self.assert_translate(self.SUPPORTED, self.SOURCE_BLANK, 0)


class AnthropicCustomModelTranslationTest(AnthropicTranslationTest):
    CONFIGURATION: ClassVar[SettingsDict] = {
        "key": "test-api-key",
        "base_url": "https://api.anthropic.com",
        "model": "custom",
        "custom_model": "claude-3-opus-20240229",
        "max_tokens": 4096,
        "persona": "",
        "style": "",
    }

    @responses.activate
    def test_clean_custom(self) -> None:
        self.mock_response()
        settings = self.CONFIGURATION.copy()
        machine = self.MACHINE_CLS
        form = machine.settings_form(machine, settings)
        self.assertTrue(form.is_valid())

        settings["model"] = "custom"
        settings["custom_model"] = ""
        form = machine.settings_form(machine, settings)
        self.assertFalse(form.is_valid())

        settings["custom_model"] = "custom-model"
        form = machine.settings_form(machine, settings)
        self.assertTrue(form.is_valid())

        settings["model"] = "claude-sonnet-4-5"
        form = machine.settings_form(machine, settings)
        self.assertFalse(form.is_valid())


class WeblateTranslationTest(FixtureComponentTestCase):
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

    @patch("weblate.machinery.weblatetm.adjust_similarity_threshold")
    def test_matches_still_probe_fuzzy_lookup(self, adjust_threshold) -> None:
        unit = Unit.objects.filter(translation__language_code="cs")[0]
        other = unit.translation.unit_set.exclude(pk=unit.pk)[0]
        other.source = unit.source
        other.target = "Preklad"
        other.state = STATE_TRANSLATED
        other.save()

        machine = WeblateTranslation({})
        machine.translate(unit, self.user)

        adjust_threshold.assert_called_once_with(0.98)


class CyrTranslitTranslationTest(ViewTestCase, BaseMachineTranslationTest):
    ENGLISH = "sr@latin"
    MACHINE_CLS = CyrTranslitTranslation
    SUPPORTED = "sr@cyrillic"
    NOTSUPPORTED = "cs"

    def test_english_map(self) -> None:
        self.skipTest("Not tested")

    def create_component(self):
        return self.create_po_new_base()

    def test_batch(self, machine=None) -> None:
        # Class does not work on mocked units
        self.skipTest("Not tested")

    def test_translate_empty(self) -> None:
        # Class does not work on mocked units
        self.skipTest("Not tested")

    def test_translate(self, **kwargs) -> None:
        # Class does not work on mocked units
        self.skipTest("Not tested")

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

    def test_fallback_language(self) -> None:
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

    def test_multiple_languages(self) -> None:
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

    def test_placeholders(self) -> None:
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

    def test_translate_escapes_html(self) -> None:
        self.ensure_dummy_mt()
        unit = self.get_unit()
        unit.target = ""
        unit.save(update_fields=["target"])

        payload = '<script>alert(1)</script>"x="y'
        source_payload = "<img/src=x/onerror=1>"

        with patch.object(
            DummyTranslation,
            "translate",
            return_value=[
                [
                    {
                        "quality": 100,
                        "plural_form": 0,
                        "service": "Dummy",
                        "text": payload,
                        "source": source_payload,
                        "original_source": "",
                    }
                ]
            ],
        ):
            response = self.client.post(
                reverse("js-translate", kwargs={"unit_id": unit.id, "service": "dummy"})
            )

        self.assertEqual(response.status_code, 200)
        translation = response.json()["translations"][0]
        self.assertEqual(
            translation["html"],
            "&lt;script&gt;alert(1)&lt;/script&gt;&quot;x=&quot;y",
        )
        self.assertEqual(
            translation["diff"],
            "<ins>&lt;script&gt;alert(1)&lt;/script&gt;&quot;x=&quot;y</ins>",
        )
        self.assertEqual(
            translation["source_diff"],
            "<ins>&lt;img/src=x/onerror=1&gt;</ins>",
        )
        self.assertNotIn("<script>", translation["html"])
        self.assertNotIn("<img", translation["source_diff"])

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


class WeblateTranslationLookupTest(SimpleTestCase):
    @patch("weblate.machinery.weblatetm.Unit.objects")
    @patch("weblate.machinery.weblatetm.Translation.objects")
    def test_get_base_queryset_uses_translation_subquery(
        self, translation_objects, unit_objects
    ) -> None:
        machine = WeblateTranslation({})
        user = MagicMock()
        translations_using = MagicMock()
        translations = MagicMock()
        filtered_translations = MagicMock()
        translation_ids = MagicMock()
        units_using = MagicMock()
        queryset = MagicMock()

        translation_objects.using.return_value = translations_using
        translations_using.all.return_value = translations
        translations.filter_access.return_value = filtered_translations
        filtered_translations.filter.return_value = translation_ids
        translation_ids.values.return_value = "translation-subquery"
        unit_objects.using.return_value = units_using
        units_using.filter.return_value = queryset

        result = machine.get_base_queryset(user, "en", "cs")

        self.assertEqual(result, queryset)
        translation_objects.using.assert_called_once_with("default")
        translations.filter_access.assert_called_once_with(user)
        filtered_translations.filter.assert_called_once_with(
            component__source_language="en",
            language="cs",
        )
        translation_ids.values.assert_called_once_with("id")
        unit_objects.using.assert_called_once_with("default")
        units_using.filter.assert_called_once_with(
            state__gte=STATE_TRANSLATED,
            translation_id__in="translation-subquery",
        )

    @patch("weblate.machinery.weblatetm.adjust_similarity_threshold")
    def test_get_matching_units_uses_fuzzy_lookup(self, adjust_threshold) -> None:
        machine = WeblateTranslation({})
        base = MagicMock()
        queryset = MagicMock()
        annotated_queryset = MagicMock()
        ordered_queryset = MagicMock()
        prepared_queryset = MagicMock()
        fuzzy_match = MagicMock(pk=1)
        base.filter.return_value = queryset
        queryset.annotate.return_value = annotated_queryset
        annotated_queryset.order_by.return_value = ordered_queryset
        prepared_queryset.iterator.return_value = [fuzzy_match]

        with patch.object(
            machine, "prepare_queryset", return_value=prepared_queryset
        ) as prepare_queryset:
            results = machine.get_matching_units(base, "Hello", 75)

        self.assertEqual(results, [fuzzy_match])
        base.filter.assert_called_once_with(source__trgm_search="Hello")
        queryset.annotate.assert_called_once()
        annotated_queryset.order_by.assert_called_once_with("-match_similarity", "pk")
        prepare_queryset.assert_called_once_with(ordered_queryset)
        prepared_queryset.iterator.assert_called_once_with(
            chunk_size=machine.candidate_limit
        )
        adjust_threshold.assert_called_once_with(0.98)

    @patch("weblate.machinery.weblatetm.adjust_similarity_threshold")
    def test_get_matching_units_orders_short_queries_before_slicing(
        self, adjust_threshold
    ) -> None:
        machine = WeblateTranslation({})
        base = MagicMock()
        short_queryset = MagicMock()
        prepared_queryset = MagicMock()
        fuzzy_match = MagicMock(pk=1)
        prepared_queryset.iterator.return_value = [fuzzy_match]

        with (
            patch.object(
                machine, "get_short_query_matches", return_value=short_queryset
            ) as get_short_query_matches,
            patch.object(
                machine, "prepare_queryset", return_value=prepared_queryset
            ) as prepare_queryset,
        ):
            results = machine.get_matching_units(base, "id", 75)

        self.assertEqual(results, [fuzzy_match])
        get_short_query_matches.assert_called_once_with(base, "id")
        prepare_queryset.assert_called_once_with(short_queryset)
        prepared_queryset.iterator.assert_called_once_with(
            chunk_size=machine.candidate_limit
        )
        adjust_threshold.assert_called_once_with(0.98)

    @patch("weblate.machinery.weblatetm.adjust_similarity_threshold")
    def test_get_matching_units_uses_exact_lookup_at_full_threshold(
        self, adjust_threshold
    ) -> None:
        machine = WeblateTranslation({})
        base = MagicMock()
        queryset = MagicMock()
        ordered_queryset = MagicMock()
        prepared_queryset = MagicMock()
        exact_match = MagicMock(pk=1)
        base.filter.return_value = queryset
        queryset.order_by.return_value = ordered_queryset
        prepared_queryset.iterator.return_value = [exact_match]

        with patch.object(
            machine, "prepare_queryset", return_value=prepared_queryset
        ) as prepare_queryset:
            results = machine.get_matching_units(base, "Hello", 100)

        self.assertEqual(results, [exact_match])
        queryset.order_by.assert_called_once_with("pk")
        prepare_queryset.assert_called_once_with(ordered_queryset)
        prepared_queryset.iterator.assert_called_once_with(
            chunk_size=machine.candidate_limit
        )
        adjust_threshold.assert_not_called()

    def test_download_translations_limits_after_filtering(self) -> None:
        machine = WeblateTranslation({})
        machine.candidate_limit = 2
        machine.comparer = MagicMock()
        machine.comparer.similarity.side_effect = [95, 90, 85]

        filtered_match = MagicMock()
        filtered_match.source_string = "ignored"
        filtered_match.all_flags = {"forbidden"}

        first_match = MagicMock()
        first_match.source_string = "first"
        first_match.all_flags = set()
        first_match.get_target_plurals.return_value = ["First"]
        first_match.translation.component = "Component"
        first_match.get_absolute_url.return_value = "/first/"

        second_match = MagicMock()
        second_match.source_string = "second"
        second_match.all_flags = set()
        second_match.get_target_plurals.return_value = ["Second"]
        second_match.translation.component = "Component"
        second_match.get_absolute_url.return_value = "/second/"

        third_match = MagicMock()
        third_match.source_string = "third"
        third_match.all_flags = set()
        third_match.get_target_plurals.return_value = ["Third"]
        third_match.translation.component = "Component"
        third_match.get_absolute_url.return_value = "/third/"

        with (
            patch.object(machine, "get_base_queryset", return_value=MagicMock()),
            patch.object(
                machine,
                "get_matching_units",
                return_value=[filtered_match, first_match, second_match, third_match],
            ),
        ):
            results = list(
                machine.download_translations(
                    "en",
                    "cs",
                    "Hello",
                    unit=None,
                    user=None,
                    threshold=10,
                )
            )

        self.assertEqual([item["text"] for item in results], ["First", "Second"])
        self.assertEqual(machine.comparer.similarity.call_count, 2)


class MachineryValidationTest(TestCase):
    def test_project_machinery_rejects_private_url(self) -> None:
        form = DeepLTranslation.settings_form(
            DeepLTranslation,
            data={"key": "x", "url": "http://127.0.0.1:11434/"},
            allow_private_targets=False,
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "internal or non-public address",
            str(form.errors["__all__"]),
        )

    def test_check_failure_hides_response_body(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = HTTPError(
            "500 Server Error: Internal Server Error for url: http://127.0.0.1/api"
        )
        response.url = "http://127.0.0.1/api"
        response.text = "aws_secret_key=AKIAIOSFODNN7EXAMPLE"
        machine = DummyTranslation({})

        with self.assertRaises(HTTPError) as raised:
            machine.check_failure(response)

        self.assertNotIn("aws_secret_key", str(raised.exception))

    def test_check_failure_shows_trusted_provider_message(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = HTTPError(
            "400 Client Error: Bad Request for url: https://api.deepl.com/v2/translate"
        )
        response.url = "https://api.deepl.com/v2/translate"
        response.json.return_value = {"message": "Auth key is invalid."}
        machine = DeepLTranslation({"key": "x", "url": "https://api.deepl.com/v2/"})

        with self.assertRaises(HTTPError) as raised:
            machine.check_failure(response)

        self.assertIn("Auth key is invalid.", str(raised.exception))

    def test_check_failure_shows_trusted_provider_plain_text_message(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = HTTPError(
            "429 Client Error: Too Many Requests for url: https://api.deepl.com/v2/translate"
        )
        response.url = "https://api.deepl.com/v2/translate"
        response.text = "Rate limit exceeded."
        response.json.side_effect = JSONDecodeError("Expecting value", "", 0)
        machine = DeepLTranslation(
            {"key": "x", "url": "https://api.deepl.com/v2/", "_project": Mock()}
        )

        with self.assertRaises(HTTPError) as raised:
            machine.check_failure(response)

        self.assertIn("Rate limit exceeded.", str(raised.exception))

    def test_check_failure_shows_fixed_provider_plain_text_message(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = HTTPError(
            "503 Server Error: Service Unavailable for url: https://translation.googleapis.com/language/translate/v2"
        )
        response.url = "https://translation.googleapis.com/language/translate/v2"
        response.text = "Service temporarily unavailable."
        response.json.side_effect = JSONDecodeError("Expecting value", "", 0)
        machine = GoogleTranslation({"key": "x", "_project": Mock()})

        with self.assertRaises(HTTPError) as raised:
            machine.check_failure(response)

        self.assertIn("Service temporarily unavailable.", str(raised.exception))

    def test_check_failure_hides_untrusted_provider_message(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = HTTPError(
            "400 Client Error: Bad Request for url: https://custom.example.com/v1"
        )
        response.url = "https://custom.example.com/v1"
        response.json.return_value = {"message": "Top secret."}
        machine = OpenAITranslation(
            {
                "key": "x",
                "model": "auto",
                "persona": "",
                "style": "",
                "base_url": "https://custom.example.com/",
                "_project": Mock(),
            }
        )

        with self.assertRaises(HTTPError) as raised:
            machine.check_failure(response)

        self.assertNotIn("Top secret.", str(raised.exception))

    def test_get_error_message_hides_untrusted_response_body(self) -> None:
        response = Mock()
        response.url = "https://custom.example.com/v1"
        response.text = "Top secret."
        response.json.return_value = {"message": "Top secret."}
        error = HTTPError(
            "400 Client Error: Bad Request for url: https://custom.example.com/v1",
            response=response,
        )
        machine = OpenAITranslation(
            {
                "key": "x",
                "model": "auto",
                "persona": "",
                "style": "",
                "base_url": "https://custom.example.com/",
                "_project": Mock(),
            }
        )

        message = machine.get_error_message(error)

        self.assertNotIn("Top secret.", message)

    def test_check_failure_does_not_trust_non_endpoint_choice_values(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = HTTPError(
            "400 Client Error: Bad Request for url: https://auto/v1"
        )
        response.url = "https://auto/v1"
        response.json.return_value = {"message": "Top secret."}
        machine = OpenAITranslation(
            {
                "key": "x",
                "model": "auto",
                "persona": "",
                "style": "",
                "base_url": "https://custom.example.com/",
                "_project": Mock(),
            }
        )

        with self.assertRaises(HTTPError) as raised:
            machine.check_failure(response)

        self.assertNotIn("Top secret.", str(raised.exception))

    @override_settings(ALLOWED_MACHINERY_DOMAINS=["api.sap.com"])
    def test_check_failure_handles_non_string_project_settings(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = HTTPError(
            "400 Client Error: Bad Request for url: https://api.sap.com/v1/translate"
        )
        response.url = "https://api.sap.com/v1/translate"
        response.json.return_value = {"message": "Invalid credentials."}
        machine = SAPTranslationHub(
            {
                "key": "x",
                "username": "",
                "password": "",
                "enable_mt": True,
                "domain": "",
                "url": "https://api.sap.com",
                "_project": Mock(),
            }
        )

        with self.assertRaises(HTTPError) as raised:
            machine.check_failure(response)

        self.assertIn("Invalid credentials.", str(raised.exception))

    def test_check_failure_shows_libretranslate_plain_text_message(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = HTTPError(
            "429 Client Error: Too Many Requests for url: https://libretranslate.com/translate"
        )
        response.url = "https://libretranslate.com/translate"
        response.text = "Too many requests."
        response.json.side_effect = JSONDecodeError("Expecting value", "", 0)
        machine = LibreTranslateTranslation(
            {"key": "", "url": "https://libretranslate.com/", "_project": Mock()}
        )

        with self.assertRaises(HTTPError) as raised:
            machine.check_failure(response)

        self.assertIn("Too many requests.", str(raised.exception))

    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
    )
    def test_project_validation_uses_runtime_url_guard(
        self, mocked_getaddrinfo
    ) -> None:
        form = DeepLTranslation.settings_form(
            DeepLTranslation,
            data={"key": "x", "url": "https://api.deepl.com/v2/"},
            allow_private_targets=False,
        )

        with patch("requests.sessions.Session.request") as mocked_request:
            self.assertFalse(form.is_valid())

        mocked_getaddrinfo.assert_called()
        mocked_request.assert_not_called()
        self.assertIn(
            "internal or non-public address",
            str(form.non_field_errors()),
        )

    @override_settings(ALLOWED_MACHINERY_DOMAINS=[".example.com"])
    def test_check_failure_shows_wildcard_allowlisted_provider_message(self) -> None:
        response = Mock()
        response.raise_for_status.side_effect = HTTPError(
            "400 Client Error: Bad Request for url: https://api.example.com/v1"
        )
        response.url = "https://api.example.com/v1"
        response.json.return_value = {"message": "Allowlisted provider error."}
        machine = OpenAITranslation(
            {
                "key": "x",
                "model": "auto",
                "persona": "",
                "style": "",
                "base_url": "https://api.example.com/",
                "_project": Mock(),
            }
        )

        with self.assertRaises(HTTPError) as raised:
            machine.check_failure(response)

        self.assertIn("Allowlisted provider error.", str(raised.exception))


class CommandTest(FixtureComponentTestCase):
    """Test for management commands."""

    def test_list_machinery(self) -> None:
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

    def test_translate(self) -> None:
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

    def test_batch_translate(self) -> None:
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
