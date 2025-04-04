# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for duplicate checks."""

from weblate.checks.duplicate import DuplicateCheck
from weblate.checks.models import Check
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit
from weblate.lang.models import Language
from weblate.trans.models import Component, Project, Translation, Unit


class DuplicateCheckTest(CheckTestCase):
    check = DuplicateCheck()

    def _run_check(self, target: str, source="", lang="cs"):
        return self.check.check_single(source, target, MockUnit(code=lang, note=""))

    def test_no_duplicated_token(self) -> None:
        self.assertFalse(self._run_check("I have two lemons"))

    def test_check_respects_boundaries_suffix(self) -> None:
        # 'lemon lemon' is a false duplicate.
        self.assertFalse(self._run_check("I have two lemon lemons"))

    def test_check_respects_boundaries_prefix(self) -> None:
        # 'melon on' is a false duplicate.
        self.assertFalse(self._run_check("I have a melon on my back"))

    def test_check_single_duplicated_token(self) -> None:
        self.assertTrue(self._run_check("I have two two lemons"))

    def test_check_multiple_duplicated_tokens(self) -> None:
        self.assertTrue(self._run_check("I have two two lemons lemons"))

    def test_check_duplicated_numbers(self) -> None:
        self.assertFalse(
            self._run_check("Mám 222 222 citrónů", source="I have 222 222 lemons")
        )

    def test_check_duplicated_letter(self) -> None:
        self.assertFalse(self._run_check("I have A A A"))

    def test_check_duplicated_source(self) -> None:
        self.assertFalse(
            self._run_check("begin begin end end", source="begin begin end end")
        )

    def test_check_duplicated_source_different(self) -> None:
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

    def test_duplicate_conjunction(self) -> None:
        self.assertFalse(
            self._run_check(
                "Zalomit řádky na 77 znacích a znacích nových řádků",
                source="Wrap lines at 77 chars and at newlines",
            )
        )

    def test_check_duplicated_language_ignore(self) -> None:
        self.assertFalse(self._run_check("Si vous vous interrogez", lang="fr"))

    def test_description(self) -> None:
        unit = Unit(
            source="string",
            target="I have two two lemons lemons",
            translation=Translation(
                language=Language("cs"),
                component=Component(
                    source_language=Language("en"), file_format="po", project=Project()
                ),
            ),
        )
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "The following words are duplicated: <code>lemons</code>, <code>two</code>",
        )
        unit.target = "I have two two"
        self.assertEqual(
            self.check.get_description(check),
            "The following word is duplicated: <code>two</code>",
        )

    def test_check_duplicated_language_cleanup(self) -> None:
        self.assertFalse(self._run_check("Cancel·la la baixada", lang="ca"))

    def test_separator(self) -> None:
        self.assertFalse(self._run_check("plug-in in"))

    def test_format_strip(self) -> None:
        self.assertTrue(self.check.check_single("", "Gruppe %Gruppe%", MockUnit()))
        self.assertFalse(
            self.check.check_single(
                "", "Gruppe %Gruppe%", MockUnit(flags="percent-placeholders")
            )
        )

    def test_same_bbcode(self) -> None:
        self.assertFalse(self.check.check_single("", "for [em]x[/em]", MockUnit()))
        self.assertTrue(self.check.check_single("", "em [em]x[/em]", MockUnit()))
        self.assertTrue(self.check.check_single("", "em [em]x", MockUnit()))
        self.assertFalse(
            self.check.check_single(
                "", "em [em]x[/em]", MockUnit(flags=["bbcode-text"])
            )
        )

    def test_duplicated_punctuation(self) -> None:
        self.assertFalse(
            self.check.check_single(
                "",
                "megjegyzéseket (a ``#`` karaktereket)",
                MockUnit(source="comments (``#`` characters)"),
            )
        )

    def test_duplicated_sentence(self) -> None:
        self.assertFalse(
            self.check.check_single(
                "",
                "Sobald diese Anfrage angenommen wird, wird der Chat als zu löschen markiert",  # codespell:ignore
                MockUnit(),
            )
        )

    def test_html_markup(self) -> None:
        self.assertEqual(
            self.check.check_single(
                "",
                "A maneira com o lobistas da indústria dos combustíveis fósseis consegues influenciar decisores políticos é um problema global. Em nenhuma parte do mundo isto é mais evidente do que na COP28, que será [presidida pelo Presidente Executivo da Companhia Nacional de Petróleo de Abu Dhabi](https://www.euronews.com/green/2023/05/24/us-and-eu-lawmakers-call-for-designated-head-of-cop28-talks-to-be-removed) - é difícil imaginar um conflito de interesses mais óbvio que este. O atual governo do Reino Unido fez poucos esforços para esconder as suas relações com os ‘think tanks’ da [Tufton Street](https://www.desmog.com/2023/04/21/tufton-street-linked-donors-have-given-630000-to-the-conservatives-since-sunak-became-prime-minister). Estes think tanks estão são altamente cuidadosos sobre revelar os seus financiadores, mas é extremamente claro quem é que o seu trabalho beneficia. O Governo do Reino Unido tem introduzido legislação anti-protesto cada vez mais draconiana, que tem sido associada a estes grupos. Defensores do clima no Reino Unido têm sido presos por [mencionar a emergência climática](https://www.opendemocracy.net/en/activists-jailed-for-seven-weeks-for-defying-ban-on-mentioning-climate-crisis) na sua defesa em tribunal. Foi instaurado um processo por desacato ao tribunal contra um manifestante pelo simples facto de [segurar um cartaz] (https://goodlawproject.org/solicitor-general-launches-proceedings-for-holding-a-placard/) à porta de um tribunal a lembrar os jurados que podiam agir de acordo com a sua consciência. É claro que a influência destes lobistas é extremamente prejudicial tanto para para a democracia como para o nosso planeta.",  # codespell:ignore
                MockUnit(code="pt"),
            ),
            {"para"},
        )

    def test_rst_markup(self) -> None:
        self.assertEqual(
            self.check.check_single(
                "This can be done in :guilabel:`Service hooks` under :guilabel:`Project settings`.",
                "Esto se puede hacer en :guilabel:`Ganchos de servicio` en :guilabel:` Configuración del proyecto` .",
                MockUnit(code="es", flags="rst-text"),
            ),
            {},
        )
