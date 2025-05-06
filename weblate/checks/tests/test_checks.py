# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helper for quality checks tests."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from django.test import SimpleTestCase
from translate.lang.data import languages

from weblate.checks.flags import Flags
from weblate.checks.format import BaseFormatCheck
from weblate.lang.models import Language, Plural

if TYPE_CHECKING:
    from weblate.checks.base import BaseCheck


class MockLanguage(Language):
    """Mock language object."""

    class Meta:
        proxy = True

    def __init__(self, code="cs") -> None:
        super().__init__(code=code)
        # We need different language codes to have different pk
        self.pk = -abs(hash(code))
        try:
            _, number, formula = languages[code]
        except KeyError:
            self.plural = Plural(language=self)
        else:
            self.plural = Plural(language=self, number=number, formula=formula)


class MockProject:
    """Mock project object."""

    def __init__(self) -> None:
        self.id = 1
        self.use_shared_tm = True
        self.name = "MockProject"
        self.slug = "mock"

    def get_glossary_tsv_cache_key(self, source_language, language) -> str:
        return f"project-glossary-tsv-test-{source_language.code}-{language.code}"

    @property
    def glossaries(self):
        return []

    @property
    def glossary_automaton(self):
        from weblate.glossary.models import get_glossary_automaton

        return get_glossary_automaton(self)


class MockComponent:
    """Mock component object."""

    def __init__(self, source_language: str = "en") -> None:
        self.id = 1
        self.source_language = MockLanguage(source_language)
        self.project = MockProject()
        self.name = "MockComponent"
        self.file_format = "auto"
        self.is_multivalue = False


class MockTranslation:
    """Mock translation object."""

    def __init__(self, code: str = "cs", source_language: str = "en") -> None:
        self.language = MockLanguage(code)
        self.component = MockComponent(source_language)
        self.is_template = False
        self.is_source = False
        self.plural = self.language.plural
        self.id = 1

    @staticmethod
    def log_debug(text, *args):
        return text % args


class MockUnit:
    """Mock unit object."""

    def __init__(
        self,
        id_hash: str | None = None,
        flags: str | Flags = "",
        code: str = "cs",
        source: str | list[str] = "",
        note: str = "",
        is_source: bool | None = None,
        target: str | list[str] = "",
        context: str = "",
    ) -> None:
        if id_hash is None:
            id_hash = random.randint(0, 65536)  # noqa: S311
        self.id_hash = id_hash
        self.flags = Flags(flags)
        self.translation = MockTranslation(code)
        if isinstance(source, str) or source is None:
            self.source = source
            self.sources = [source]
        else:
            self.source = source[0]
            self.sources = source
        self.fuzzy = False
        self.translated = True
        self.readonly = False
        self.state = 20
        if isinstance(target, str):
            self.target = target
            self.targets = [target]
        else:
            self.target = target[0]
            self.targets = target
        self.note = note
        self.check_cache = {}
        self.machinery = {}
        self.is_source = is_source
        self.context = context
        self.glossary_terms = None

    @property
    def all_flags(self):
        return self.flags

    def get_source_plurals(self):
        return self.sources

    def get_target_plurals(self):
        return self.targets

    @property
    def source_string(self):
        return self.source


class CheckTestCase(SimpleTestCase, ABC):
    """Generic test, also serves for testing base class."""

    default_lang = "cs"

    def setUp(self) -> None:
        self.test_empty: tuple[str, str, str] = ("", "", "")
        self.test_good_matching: tuple[str, str, str] = ("string", "string", "")
        self.test_good_none: tuple[str, str, str] = ("string", "string", "")
        self.test_good_ignore: tuple[str, str, str] | None = None
        self.test_good_flag: tuple[str, str, str] | None = None
        self.test_failure_1: tuple[str, str, str] | None = None
        self.test_failure_2: tuple[str, str, str] | None = None
        self.test_failure_3: tuple[str, str, str] | None = None
        self.test_ignore_check: tuple[str, str, str] = (
            "x",
            "x",
            self.check.ignore_string if self.check else "",
        )
        self.test_highlight: tuple[str, str, list[tuple[int, int, str]]] | None = None

    @property
    @abstractmethod
    def check(self) -> BaseCheck:
        raise NotImplementedError

    def do_test(
        self, expected: bool, data: tuple[str, str, str] | None, lang: str | None = None
    ):
        """Perform single check if we have data to test."""
        if data is None:
            self.skipTest("Not supported")
        if isinstance(self.check, BaseFormatCheck):
            self.skipTest("Not supported")
        if lang is None:
            lang = self.default_lang
        params = '"{}"/"{}" ({})'.format(*data)

        unit = MockUnit(None, data[2], lang, source=data[0])

        # Verify skip logic
        should_skip = self.check.should_skip(unit)
        if expected:
            self.assertFalse(should_skip, msg=f"Check should not skip for {params}")
        elif should_skip:
            # There is nothing to test here
            return None

        # Verify check logic
        result = self.check.check_single(
            data[0][0] if isinstance(data[0], list) else data[0], data[1], unit
        )
        if expected:
            self.assertTrue(result, msg=f"Check did not fire for {params}")
        else:
            self.assertFalse(result, msg=f"Check did fire for {params}")
        return result

    def test_single_good_matching(self) -> None:
        self.do_test(False, self.test_good_matching)

    def test_single_good_none(self) -> None:
        self.do_test(False, self.test_good_none)

    def test_single_good_ignore(self) -> None:
        self.do_test(False, self.test_good_ignore)

    def test_single_empty(self) -> None:
        self.do_test(False, self.test_empty)

    def test_single_failure_1(self) -> None:
        self.do_test(True, self.test_failure_1)

    def test_single_failure_2(self) -> None:
        self.do_test(True, self.test_failure_2)

    def test_single_failure_3(self) -> None:
        self.do_test(True, self.test_failure_3)

    def test_check_good_flag(self) -> None:
        if self.test_good_flag is None:
            self.skipTest("Not supported")
        self.assertFalse(
            self.check.check_target(
                [self.test_good_flag[0]],
                [self.test_good_flag[1]],
                MockUnit(
                    None,
                    self.test_good_flag[2],
                    self.default_lang,
                    source=self.test_good_flag[0],
                ),
            )
        )

    def test_check_good_matching_singular(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching[0]],
                [self.test_good_matching[1]],
                MockUnit(
                    None,
                    self.test_good_matching[2],
                    self.default_lang,
                    source=self.test_good_matching[0],
                ),
            )
        )

    def test_check_good_none_singular(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_good_none[0]],
                [self.test_good_none[1]],
                MockUnit(
                    None,
                    self.test_good_none[2],
                    self.default_lang,
                    source=self.test_good_none[0],
                ),
            )
        )

    def test_check_good_ignore_singular(self) -> None:
        if self.test_good_ignore is None:
            self.skipTest("Not supported")
        self.assertFalse(
            self.check.check_target(
                [self.test_good_ignore[0]],
                [self.test_good_ignore[1]],
                MockUnit(
                    None,
                    self.test_good_ignore[2],
                    self.default_lang,
                    source=self.test_good_ignore[0],
                ),
            )
        )

    def test_check_good_matching_plural(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching[0]] * 2,
                [self.test_good_matching[1]] * 3,
                MockUnit(
                    None,
                    self.test_good_matching[2],
                    self.default_lang,
                    source=self.test_good_matching[0],
                ),
            )
        )

    def test_check_failure_1_singular(self) -> None:
        if self.test_failure_1 is None:
            self.skipTest("Not supported")
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_1[0]],
                [self.test_failure_1[1]],
                MockUnit(
                    None,
                    self.test_failure_1[2],
                    self.default_lang,
                    source=self.test_failure_1[0],
                ),
            )
        )

    def test_check_failure_1_plural(self) -> None:
        if self.test_failure_1 is None:
            self.skipTest("Not supported")
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_1[0]] * 2,
                [self.test_failure_1[1]] * 3,
                MockUnit(
                    None,
                    self.test_failure_1[2],
                    self.default_lang,
                    source=self.test_failure_1[0],
                ),
            )
        )

    def test_check_failure_2_singular(self) -> None:
        if self.test_failure_2 is None:
            self.skipTest("Not supported")
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_2[0]],
                [self.test_failure_2[1]],
                MockUnit(
                    None,
                    self.test_failure_2[2],
                    self.default_lang,
                    source=self.test_failure_2[0],
                ),
            )
        )

    def test_check_failure_3_singular(self) -> None:
        if self.test_failure_3 is None:
            self.skipTest("Not supported")
        self.assertTrue(
            self.check.check_target(
                [self.test_failure_3[0]],
                [self.test_failure_3[1]],
                MockUnit(
                    None,
                    self.test_failure_3[2],
                    self.default_lang,
                    source=self.test_failure_3[0],
                ),
            )
        )

    def test_check_ignore_check(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_ignore_check[0]] * 2,
                [self.test_ignore_check[1]] * 3,
                MockUnit(
                    None,
                    self.test_ignore_check[2],
                    self.default_lang,
                    source=self.test_ignore_check[0],
                ),
            )
        )

    def test_check_highlight(self) -> None:
        if self.test_highlight is None:
            self.skipTest("Not supported")
        unit = MockUnit(
            None,
            self.test_highlight[0],
            self.default_lang,
            source=self.test_highlight[1],
        )
        self.assertEqual(
            list(self.check.check_highlight(self.test_highlight[1], unit)),
            self.test_highlight[2],
        )
