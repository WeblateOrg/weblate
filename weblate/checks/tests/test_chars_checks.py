# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for char based quality checks."""

from django.test import SimpleTestCase

from weblate.checks.chars import (
    BeginNewlineCheck,
    BeginSpaceCheck,
    DoubleSpaceCheck,
    EndColonCheck,
    EndEllipsisCheck,
    EndExclamationCheck,
    EndInterrobangCheck,
    EndNewlineCheck,
    EndQuestionCheck,
    EndSemicolonCheck,
    EndSpaceCheck,
    EndStopCheck,
    EscapedNewlineCountingCheck,
    KabyleCharactersCheck,
    KashidaCheck,
    MaxLengthCheck,
    MultipleCapitalCheck,
    NewLineCountCheck,
    PunctuationSpacingCheck,
    ZeroWidthSpaceCheck,
)
from weblate.checks.models import Check
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit
from weblate.lang.models import Language
from weblate.trans.models import Component, Project, Translation, Unit


class BeginNewlineCheckTest(CheckTestCase):
    check = BeginNewlineCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("\nstring", "\nstring", "")
        self.test_failure_1 = ("\nstring", " \nstring", "")
        self.test_failure_2 = ("string", "\nstring", "")


class EndNewlineCheckTest(CheckTestCase):
    check = EndNewlineCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string\n", "string\n", "")
        self.test_failure_1 = ("string\n", "string", "")
        self.test_failure_2 = ("string", "string\n", "")


class BeginSpaceCheckTest(CheckTestCase):
    check = BeginSpaceCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("   string", "   string", "")
        self.test_good_ignore = (".", " ", "")
        self.test_good_none = (" The ", "  ", "")
        self.test_failure_1 = ("  string", "    string", "")
        self.test_failure_2 = ("    string", "  string", "")


class EndSpaceCheckTest(CheckTestCase):
    check = EndSpaceCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string  ", "string  ", "")
        self.test_good_ignore = (".", " ", "")
        self.test_good_none = (" The ", "  ", "")
        self.test_failure_1 = ("string  ", "string", "")
        self.test_failure_2 = ("string", "string ", "")


class DoubleSpaceCheckTest(CheckTestCase):
    check = DoubleSpaceCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string  string", "string  string", "")
        self.test_good_ignore = ("  ", " ", "")
        self.test_failure_1 = ("string string", "string  string", "")


class EndStopCheckTest(CheckTestCase):
    check = EndStopCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string.", "string.", "")
        self.test_good_ignore = (".", " ", "")
        self.test_failure_1 = ("string.", "string", "")
        self.test_failure_2 = ("string", "string.", "")

    def test_arabic(self) -> None:
        self.assertTrue(
            self.check.check_target(
                ["<unused singular (hash=…)>", "Lorem ipsum dolor sit amet."],
                ["zero", "one", "two", "few", "many", "other"],
                MockUnit(code="ar"),
            )
        )
        self.assertFalse(
            self.check.check_target(
                ["<unused singular (hash=…)>", "Lorem ipsum dolor sit amet."],
                ["zero.", "one", "two.", "few.", "many.", "other."],
                MockUnit(code="ar"),
            )
        )

    def test_japanese(self) -> None:
        self.do_test(False, ("Text:", "Text。", ""), "ja")
        self.do_test(True, ("Text:", "Text", ""), "ja")
        self.assertTrue(
            self.check.check_target(
                ["<unused singular (hash=…)>", "English."],
                ["Japanese…"],
                MockUnit(code="ja"),
            )
        )
        self.assertFalse(
            self.check.check_target(
                ["<unused singular (hash=…)>", "English."],
                ["Japanese。"],
                MockUnit(code="ja"),
            )
        )

    def test_hindi(self) -> None:
        self.do_test(False, ("Text.", "Text।", ""), "hi")
        self.do_test(True, ("Text.", "Text", ""), "hi")

    def test_armenian(self) -> None:
        self.do_test(False, ("Text:", "Text`", ""), "hy")
        self.do_test(False, ("Text:", "Text՝", ""), "hy")
        self.do_test(True, ("Text.", "Text", ""), "hy")

    def test_santali(self) -> None:
        self.do_test(False, ("Text.", "Text.", ""), "sat")
        self.do_test(False, ("Text.", "Text᱾", ""), "sat")
        self.do_test(True, ("Text.", "Text", ""), "sat")

    def test_my(self) -> None:
        self.do_test(False, ("Te xt", "Te xt", ""), "my")  # codespell:ignore
        self.do_test(True, ("Te xt", "Te xt။", ""), "my")  # codespell:ignore
        self.do_test(False, ("Text.", "Text။", ""), "my")
        self.do_test(False, ("Text?", "ပုံဖျက်မလး။", ""), "my")
        self.do_test(False, ("Te xt", "ပုံဖျက်မလး။", ""), "my")  # codespell:ignore

    def test_french(self) -> None:
        self.do_test(
            False,
            (
                "To enable password-less login, the public SSH key can be copied to the remote host.",
                "Pour activer l’authentification sans mot de passe, la clé publique SSH peut être copiée sur le serveur distant.",  # codespell:ignore
                "",
            ),
            "fr",
        )


class EndColonCheckTest(CheckTestCase):
    check = EndColonCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string:", "string:", "")
        self.test_failure_1 = ("string:", "string", "")
        self.test_failure_2 = ("string", "string:", "")

    def test_hy(self) -> None:
        self.do_test(False, ("Text:", "Texte՝", ""), "hy")
        self.do_test(True, ("Text:", "Texte", ""), "hy")
        self.do_test(False, ("Text", "Texte:", ""), "hy")

    def test_japanese(self) -> None:
        self.do_test(False, ("Text:", "Texte。", ""), "ja")

    def test_japanese_ignore(self) -> None:
        self.do_test(False, ("Text", "Texte", ""), "ja")


class EndQuestionCheckTest(CheckTestCase):
    check = EndQuestionCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string?", "string?", "")
        self.test_failure_1 = ("string?", "string", "")
        self.test_failure_2 = ("string", "string?", "")

    def test_hy(self) -> None:
        self.do_test(False, ("Text?", "Texte՞", ""), "hy")
        self.do_test(True, ("Text?", "Texte", ""), "hy")
        self.do_test(False, ("Text", "Texte?", ""), "hy")

    def test_greek(self) -> None:
        self.do_test(False, ("Text?", "Texte;", ""), "el")
        self.do_test(False, ("Text?", "Texte;", ""), "el")

    def test_greek_ignore(self) -> None:
        self.do_test(False, ("Text", "Texte", ""), "el")

    def test_greek_wrong(self) -> None:
        self.do_test(True, ("Text?", "Texte", ""), "el")

    def test_my(self) -> None:
        self.do_test(False, ("Texte", "Texte", ""), "my")
        self.do_test(False, ("Text?", "ပုံဖျက်မလား။", ""), "my")
        self.do_test(True, ("Te xt", "ပုံဖျက်မလား။", ""), "my")  # codespell:ignore

    def test_interrobang(self) -> None:
        self.do_test(False, ("string!?", "string?", ""))
        self.do_test(False, ("string?", "string?!", ""))
        self.do_test(False, ("string؟!", "string?", ""))
        self.do_test(False, ("string?", "string!؟", ""))
        self.do_test(False, ("string⁈", "string?", ""))
        self.do_test(False, ("string?", "string⁉", ""))
        self.do_test(False, ("string？！", "string?", ""))
        self.do_test(False, ("string?", "string！？", ""))


class EndExclamationCheckTest(CheckTestCase):
    check = EndExclamationCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string!", "string!", "")
        self.test_failure_1 = ("string!", "string", "")
        self.test_failure_2 = ("string", "string!", "")

    def test_hy(self) -> None:
        self.do_test(False, ("Text!", "Texte՜", ""), "hy")
        self.do_test(False, ("Text!", "Texte", ""), "hy")
        self.do_test(False, ("Text", "Texte!", ""), "hy")

    def test_eu(self) -> None:
        self.do_test(False, ("Text!", "¡Texte!", ""), "eu")

    def test_interrobang(self) -> None:
        self.do_test(False, ("string!?", "string!", ""))
        self.do_test(False, ("string!", "string?!", ""))
        self.do_test(False, ("string!؟", "string!", ""))
        self.do_test(False, ("string!", "string؟!", ""))
        self.do_test(False, ("string⁈", "string!", ""))
        self.do_test(False, ("string!", "string⁉", ""))
        self.do_test(False, ("string？！", "string!", ""))
        self.do_test(False, ("string!", "string！？", ""))


class EndInterrobangCheckTest(CheckTestCase):
    check = EndInterrobangCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string!?", "string?!", "")
        self.test_failure_1 = ("string!?", "string?", "")
        self.test_failure_2 = ("string!?", "string!", "")
        self.test_failure_3 = ("string!", "string!?", "")

    def test_translate(self) -> None:
        self.do_test(False, ("string!?", "string!?", ""))
        self.do_test(False, ("string?!", "string؟!", ""))
        self.do_test(False, ("string!?", "string!؟", ""))
        self.do_test(False, ("string⁉", "string⁈", ""))
        self.do_test(False, ("string⁉", "string⁉", ""))
        self.do_test(False, ("string！？", "string！？", ""))
        self.do_test(False, ("string！？", "string？！", ""))
        self.do_test(False, ("string?!", "string？！", ""))
        self.do_test(False, ("string！？", "string!?", ""))
        self.do_test(True, ("string?", "string?!", ""))
        self.do_test(True, ("string?", "string؟!", ""))
        self.do_test(False, ("string⁉", "string!?", ""))
        self.do_test(False, ("string?!", "string⁈", ""))
        self.do_test(False, ("string？！", "string⁈", ""))


class EndEllipsisCheckTest(CheckTestCase):
    check = EndEllipsisCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string…", "string…", "")
        self.test_failure_1 = ("string…", "string...", "")
        self.test_failure_2 = ("string.", "string…", "")
        self.test_failure_3 = ("string..", "string…", "")

    def test_translate(self) -> None:
        self.do_test(False, ("string...", "string…", ""))


class EscapedNewlineCountingCheckTest(CheckTestCase):
    check = EscapedNewlineCountingCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string\\nstring", "string\\nstring", "")
        self.test_good_none = (r"C:\\path\name", r"C:\\path\jmeno", "")
        self.test_failure_1 = ("string\\nstring", "string\\n\\nstring", "")
        self.test_failure_2 = ("string\\n\\nstring", "string\\nstring", "")


class NewLineCountCheckTest(CheckTestCase):
    check = NewLineCountCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_single_good_matching = ("string\n\nstring", "string\n\nstring", "")
        self.test_failure_1 = ("string\nstring", "string\n\n\nstring", "")
        self.test_failure_2 = ("string\nstring\n\nstring", "string\nstring\nstring", "")


class ZeroWidthSpaceCheckTest(CheckTestCase):
    check = ZeroWidthSpaceCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("str\u200bing", "str\u200bing", "")
        self.test_good_none = ("str\u200bing", "string", "")
        self.test_failure_1 = ("string", "str\u200bing", "")


class MaxLengthCheckTest(SimpleTestCase):
    def setUp(self) -> None:
        self.check = MaxLengthCheck()
        self.test_good_matching = ("strings", "less than 21", "max-length:12")
        self.test_good_matching_unicode = ("strings", "less than 21", "max-length:12")

    def test_check(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching[0]],
                [self.test_good_matching[1]],
                MockUnit(flags=self.test_good_matching[2]),
            )
        )

    def test_check_invalid_flag(self) -> None:
        self.assertTrue(
            self.check.check_target(
                [self.test_good_matching[0]],
                [self.test_good_matching[1]],
                MockUnit(flags="max-length:*"),
            )
        )

    def test_description_invalid_flag(self) -> None:
        unit = Unit(
            source=self.test_good_matching[0],
            target=self.test_good_matching[1],
            extra_flags="max-length:*",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language(code="en"),
                    project=Project(),
                )
            ),
        )
        check = Check(unit=unit)
        self.assertIn(
            "Could not parse max-length flag:", str(self.check.get_description(check))
        )

    def test_unicode_check(self) -> None:
        self.assertFalse(
            self.check.check_target(
                [self.test_good_matching_unicode[0]],
                [self.test_good_matching_unicode[1]],
                MockUnit(flags=self.test_good_matching_unicode[2]),
            )
        )

    def test_failure_check(self) -> None:
        self.assertTrue(
            self.check.check_target(
                [self.test_good_matching[0]],
                [self.test_good_matching[1]],
                MockUnit(flags="max-length:10"),
            )
        )

    def test_failure_unicode_check(self) -> None:
        self.assertTrue(
            self.check.check_target(
                [self.test_good_matching_unicode[0]],
                [self.test_good_matching_unicode[1]],
                MockUnit(flags="max-length:10"),
            )
        )

    def test_replace_check(self) -> None:
        self.assertFalse(
            self.check.check_target(
                ["hi %s"],
                ["ahoj %s"],
                MockUnit(flags="max-length:10"),
            )
        )
        self.assertTrue(
            self.check.check_target(
                ["hi %s"],
                ["ahoj %s"],
                MockUnit(flags='max-length:10, replacements:%s:"very long text"'),
            )
        )

    def test_replace_xml_check(self) -> None:
        self.assertTrue(
            self.check.check_target(
                ["hi <mrk>%s</mrk>"],
                ["ahoj <mrk>%s</mrk>"],
                MockUnit(flags="max-length:10"),
            )
        )
        self.assertFalse(
            self.check.check_target(
                ["hi <mrk>%s</mrk>"],
                ["ahoj <mrk>%s</mrk>"],
                MockUnit(flags="max-length:10, xml-text"),
            )
        )
        self.assertTrue(
            self.check.check_target(
                ["hi <mrk>%s</mrk>"],
                ["ahoj <mrk>%s</mk>"],
                MockUnit(flags="max-length:10, xml-text"),
            )
        )


class EndSemicolonCheckTest(CheckTestCase):
    check = EndSemicolonCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string;", "string;", "")
        self.test_failure_1 = ("string;", "string", "")
        self.test_failure_2 = ("string:", "string;", "")
        self.test_failure_3 = ("string", "string;", "")

    def test_greek(self) -> None:
        self.do_test(False, ("Text?", "Texte;", ""), "el")

    def test_xml(self) -> None:
        self.do_test(False, ("Text", "Texte&amp;", ""))


class KashidaCheckTest(CheckTestCase):
    check = KashidaCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string", "string", "")
        self.test_good_ignore = ("string", "بـ:", "")
        self.test_failure_1 = ("string", "string\u0640", "")
        self.test_failure_2 = ("string", "string\ufe79", "")
        self.test_failure_3 = ("string", "string\ufe7f", "")


class PunctuationSpacingCheckTest(CheckTestCase):
    check = PunctuationSpacingCheck()
    default_lang = "fr"

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = (
            "string? string?! string! string: string;",
            "string ? string ?! string\u202f! string&nbsp;; string\u00a0:",
            "",
        )
        self.test_good_none = (
            "string &end; http://example.com",
            "string &end; &amp; http://example.com",
            "",
        )
        self.test_failure_1 = ("string", "string!", "")
        self.test_failure_2 = ("string", "string\u00a0? string;", "")
        self.test_failure_3 = ("string", "string\u00a0; string?", "")

    def test_fr_ca(self) -> None:
        self.do_test(True, ("string", "string!", ""), "fr")
        self.do_test(False, ("string", "string!", ""), "fr_CA")

    def test_markdown(self) -> None:
        self.do_test(
            True,
            (
                "🎉 [Fedora Linux 39 released!](https://fedoramagazine.org/announcing-fedora-linux-39)",
                "🎉 [Fedora Linux 39 est sortie!](https://fedoramagazine.org/announcing-fedora-linux-39)",
                "md-text",
            ),
            "fr",
        )
        self.do_test(
            False,
            (
                "🎉 [Fedora Linux 39 released!](https://fedoramagazine.org/announcing-fedora-linux-39)",
                "🎉 [Fedora Linux 39 est sortie !](https://fedoramagazine.org/announcing-fedora-linux-39)",
                "md-text",
            ),
            "fr",
        )

    def test_restructured_text(self) -> None:
        self.do_test(
            True,
            (
                ":ref:`document` here",
                ":ref:`document` tam",
                "",
            ),
            "fr",
        )
        self.do_test(
            False,
            (
                ":ref:`document` here",
                ":ref:`document` tam",
                "rst-text",
            ),
            "fr",
        )

    def test_angular_fr_placeholders(self) -> None:
        # XLIFF placeholder regex so highlight_string skips equiv-text content
        xliff_placeholder = r'placeholders:r"<x\s[^>]*/>"'
        # Check should not fire when punctuation is inside placeholder equiv-text
        self.do_test(
            False,
            (
                'Orangutan has <x id="INTERPOLATION" equiv-text="{{ count | other: 0 }}"/> banana.\n',
                'Orangutan a <x id="INTERPOLATION" equiv-text="{{ count | other: 0 }}"/> banane.\n',
                xliff_placeholder,
            ),
            "fr",
        )
        # Check should fire when punctuation is outside placeholder
        self.do_test(
            True,
            (
                'Orangutan has: <x id="INTERPOLATION" equiv-text="{{ count }}"/> banana.\n',
                'Orangutan a: <x id="INTERPOLATION" equiv-text="{{ count }}"/> banane.\n',
                xliff_placeholder,
            ),
            "fr",
        )

    def test_cdata(self) -> None:
        self.do_test(
            False,
            (
                "<![CDATA[Auto-run is <i>enabled</i>]]>",
                "<![CDATA[Auto-run is <i>enabled</i>]]>",
                "",
            ),
            "fr",
        )


class KabyleCharactersCheckTest(CheckTestCase):
    check = KabyleCharactersCheck()
    default_lang = "kab"

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string", "string", "")
        self.test_failure_1 = ("string", "γ", "")
        self.test_failure_2 = ("string", "Γ", "")
        self.test_failure_3 = ("string", "ε", "")

    def test_skip(self) -> None:
        self.do_test(
            False,
            (
                "string",
                "γΓε",
                "",
            ),
            "el",
        )


class MultipleCapitalCheckTest(CheckTestCase):
    check = MultipleCapitalCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("Hello", "Hello", "")
        self.test_failure_1 = ("Hello", "HEllo", "")
        self.test_failure_2 = ("camel case", "CAmelCase", "")
        self.test_failure_3 = ("sigma", "ΣIGMA", "")

    def test_acronyms(self) -> None:
        self.do_test(
            False,
            (
                "Welcome NATO",
                "Bonjour OTAN",
                "",
            ),
            "fr",
        )
        self.do_test(
            False,
            (
                "Welcome NATO",
                "Vítej NATO",
                "",
            ),
            "cs",
        )

    def test_translation(self) -> None:
        self.do_test(
            False,
            (
                "Hello world",
                "שלום עולם (World)",
                "",
            ),
            "he",
        )
