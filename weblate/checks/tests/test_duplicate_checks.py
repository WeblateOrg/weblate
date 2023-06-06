# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for duplicate checks."""

from weblate.checks.duplicate import DuplicateCheck
from weblate.checks.models import Check
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit
from weblate.lang.models import Language
from weblate.trans.models import Component, Translation, Unit


class DuplicateCheckTest(CheckTestCase):
    check = DuplicateCheck()

    def _run_check(self, target, source="", lang="cs"):
        return self.check.check_single(source, target, MockUnit(code=lang, note=""))

    def test_no_duplicated_token(self):
        self.assertFalse(self._run_check("I have two lemons"))

    def test_check_respects_boundaries_suffix(self):
        # 'lemon lemon' is a false duplicate.
        self.assertFalse(self._run_check("I have two lemon lemons"))

    def test_check_respects_boundaries_prefix(self):
        # 'melon on' is a false duplicate.
        self.assertFalse(self._run_check("I have a melon on my back"))

    def test_check_single_duplicated_token(self):
        self.assertTrue(self._run_check("I have two two lemons"))

    def test_check_multiple_duplicated_tokens(self):
        self.assertTrue(self._run_check("I have two two lemons lemons"))

    def test_check_duplicated_numbers(self):
        self.assertFalse(
            self._run_check("Mám 222 222 citrónů", source="I have 222 222 lemons")
        )

    def test_check_duplicated_letter(self):
        self.assertFalse(self._run_check("I have A A A"))

    def test_check_duplicated_source(self):
        self.assertFalse(
            self._run_check("begin begin end end", source="begin begin end end")
        )

    def test_check_duplicated_source_different(self):
        self.assertFalse(
            self._run_check("ХАХ ХАХ! ХЕ ХЕ ХЕ!", source="HAH HAH! HEH HEH HEH!")
        )
        self.assertTrue(self._run_check("ХАХ ХАХ!", source="HAH HAH! HEH HEH HEH!"))
        self.assertTrue(
            self._run_check("ХАХ ХАХ! ХЕ ХЕ ХЕ! ХИ ХИ!", source="HAH HAH! HEH HEH HEH!")
        )
        self.assertTrue(
            self._run_check("ХАХ ХАХ! ХЕ ХЕ!", source="HAH HAH! HEH HEH HEH!")
        )
        self.assertTrue(
            self._run_check("ХАХ ХАХ ХАХ! ХЕ ХЕ ХЕ!", source="HAH HAH! HEH HEH HEH!")
        )

    def test_duplicate_conjunction(self):
        self.assertFalse(
            self._run_check(
                "Zalomit řádky na 77 znacích a znacích nových řádků",
                source="Wrap lines at 77 chars and at newlines",
            )
        )

    def test_check_duplicated_language_ignore(self):
        self.assertFalse(self._run_check("Si vous vous interrogez", lang="fr"))

    def test_description(self):
        unit = Unit(
            source="string",
            target="I have two two lemons lemons",
            translation=Translation(
                language=Language("cs"),
                component=Component(source_language=Language("en"), file_format="po"),
            ),
        )
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "Text contains the same word twice in a row: lemons, two",
        )

    def test_check_duplicated_language_cleanup(self):
        self.assertFalse(self._run_check("Cancel·la la baixada", lang="ca"))

    def test_separator(self):
        self.assertFalse(self._run_check("plug-in in"))

    def test_format_strip(self):
        self.assertTrue(self.check.check_single("", "Gruppe %Gruppe%", MockUnit()))
        self.assertFalse(
            self.check.check_single(
                "", "Gruppe %Gruppe%", MockUnit(flags="percent-placeholders")
            )
        )

    def test_same_bbcode(self):
        self.assertFalse(self.check.check_single("", "for [em]x[/em]", MockUnit()))
        self.assertTrue(self.check.check_single("", "em [em]x[/em]", MockUnit()))
        self.assertTrue(self.check.check_single("", "em [em]x", MockUnit()))

    def test_duplicated_punctuation(self):
        self.assertFalse(
            self.check.check_single(
                "",
                "megjegyzéseket (a ``#`` karaktereket)",
                MockUnit(source="comments (``#`` characters)"),
            )
        )

    def test_duplicated_sentence(self):
        self.assertFalse(
            self.check.check_single(
                "",
                "Sobald diese Anfrage angenommen wird, wird der Chat als zu löschen markiert",
                MockUnit(),
            )
        )
