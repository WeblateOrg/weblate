# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from random import choice
from typing import TYPE_CHECKING

from weblate.checks.glossary import GlossaryCheck, ProhibitedInitialCharacterCheck
from weblate.checks.models import Check
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.csv import PROHIBITED_INITIAL_CHARS
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.trans.models import Unit


class GlossaryCheckTest(ViewTestCase):
    check = GlossaryCheck()
    CREATE_GLOSSARIES = True

    def setUp(self) -> None:
        super().setUp()
        self.unit = self.get_unit()
        self.unit.extra_flags = "check-glossary"
        self.unit.translate(self.user, "Ahoj světe!\n", STATE_TRANSLATED)
        # Clear unit caches
        self.unit.check_cache = {}
        self.unit.glossary_terms = None
        self.glossary = self.project.glossaries[0].translation_set.get(
            language=self.unit.translation.language
        )

    def add_glossary(self, target: str, context="") -> None:
        self.glossary.add_unit(None, context, "hello", target)

    def test_missing(self) -> None:
        self.assertFalse(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_good(self) -> None:
        self.add_glossary("ahoj")
        self.assertFalse(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_case_insensitive(self) -> None:
        self.add_glossary("Ahoj")
        self.assertFalse(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_forbidden(self) -> None:
        self.add_glossary("ahoj")
        self.glossary.unit_set.all().update(extra_flags="forbidden")
        self.assertTrue(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_bad(self) -> None:
        self.add_glossary("nazdar")
        self.assertTrue(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_multi(self) -> None:
        self.add_glossary("nazdar")
        self.add_glossary("ahoj", "2")
        self.assertFalse(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_description(self) -> None:
        self.test_bad()
        check = Check(unit=self.unit)
        self.assertEqual(
            self.check.get_description(check),
            "Following terms are not translated according to glossary: hello",
        )


class ProhibitedInitialCharacterCheckTest(ViewTestCase):
    check = ProhibitedInitialCharacterCheck()
    CREATE_GLOSSARIES = True

    def setUp(self) -> None:
        """Set up the test."""
        super().setUp()
        self.glossary = self.project.glossaries[0].translation_set.get(
            language_code="cs"
        )

    def add_glossary(self, source: str) -> Unit:
        """Add a glossary term."""
        return self.glossary.add_unit(None, context="", source=source, target=source)

    def get_term(self) -> str:
        char = choice(list(PROHIBITED_INITIAL_CHARS))  # noqa: S311
        return f"{char} glossary term"

    def test_prohibited_initial_character(self) -> None:
        """Check that the check identifies prohibited characters."""
        valid_unit = self.add_glossary("glossary term")
        self.assertEqual(Check.objects.filter(name=self.check.check_id).count(), 0)
        self.assertFalse(
            self.check.check_target(["glossary term"], ["glossary term"], valid_unit)
        )

        term = self.get_term()
        unit = self.add_glossary(term)
        self.assertEqual(Check.objects.filter(name=self.check.check_id).count(), 2)
        self.assertTrue(self.check.check_target([term], [term], unit))

    def test_ignore_prohibited_initial_character(self) -> None:
        """Check that the check can be ignored with flag."""
        term = self.get_term()
        unit = self.add_glossary(term)
        unit.extra_flags = "ignore-prohibited-initial-character"

        # reset all_flags to reset cached_property
        unit.all_flags = unit.get_all_flags()
        self.assertFalse(self.check.check_target([term], [term], unit))

    def test_non_glossary(self) -> None:
        self.assertEqual(Check.objects.filter(name=self.check.check_id).count(), 0)
        translation = self.get_translation()
        term = self.get_term()
        translation.add_unit(None, context="", source=term, target=term)
        self.assertEqual(Check.objects.filter(name=self.check.check_id).count(), 0)
