# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for quality checks."""

from weblate.checks.same import SameCheck
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_TRANSLATED


class SameCheckTest(CheckTestCase):
    check = SameCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_none = ("%(source)s", "%(source)s", "python-format")
        self.test_good_matching = ("source", "translation", "")
        self.test_good_ignore = ("alarm", "alarm", "")
        self.test_failure_1 = ("retezec", "retezec", "")

    def test_same_source_language(self) -> None:
        unit = MockUnit(code="en")
        # Is template
        unit.translation.is_template = True
        unit.translation.is_source = True
        unit.is_source = True
        self.assertTrue(self.check.should_skip(unit))
        # Is same as source
        unit.translation.template = False
        self.assertTrue(self.check.should_skip(unit))
        # Interlingua special case
        unit.translation.language.code = "ia"
        self.assertTrue(self.check.should_skip(unit))

    def test_same_db_screen(self) -> None:
        self.assertTrue(
            self.check.check_single(
                "some long text is here", "some long text is here", MockUnit(code="de")
            )
        )
        self.assertFalse(
            self.check.check_single(
                "some long text is here",
                "some long text is here",
                MockUnit(code="de", note="Tag: screen"),
            )
        )

    def test_same_numbers(self) -> None:
        self.do_test(False, ("1:4", "1:4", ""))
        self.do_test(False, ("1, 3, 10", "1, 3, 10", ""))

    def test_same_strict(self) -> None:
        self.do_test(True, ("Linux kernel", "Linux kernel", "strict-same"))

    def test_same_multi(self) -> None:
        self.do_test(False, ("Linux kernel", "Linux kernel", ""))
        self.do_test(
            True, ("Linux kernel testing image", "Linux kernel testing image", "")
        )
        self.do_test(False, ("Gettext (PO)", "Gettext (PO)", ""))
        self.do_test(
            False, ("powerpc, m68k, i386, amd64", "powerpc, m68k, i386, amd64", "")
        )

        self.do_test(False, ("Fedora &amp; openSUSE", "Fedora &amp; openSUSE", ""))

        self.do_test(False, ("n/a mm", "n/a mm", ""))

        self.do_test(False, ("i18n", "i18n", ""))

        self.do_test(False, ("i18next", "i18next", ""))

    def test_same_copyright(self) -> None:
        self.do_test(
            False,
            (
                "(c) Copyright © 2013–2023 Michal Čihař",
                "(c) Copyright © 2013–2023 Michal Čihař",
                "",
            ),
        )
        self.do_test(
            False,
            (
                "© Copyright © 2013–2023 Michal Čihař",
                "© Copyright © 2013–2023 Michal Čihař",
                "",
            ),
        )

    def test_same_format(self) -> None:
        self.do_test(False, ("%d.%m.%Y, %H:%M", "%d.%m.%Y, %H:%M", "php-format"))

        self.do_test(True, ("%d bajt", "%d bajt", "php-format"))

        self.do_test(False, ("%d table(s)", "%d table(s)", "php-format"))

        self.do_test(
            False,
            ("%s %s %s %s %s %s &nbsp; %s", "%s %s %s %s %s %s &nbsp; %s", "c-format"),
        )

        self.do_test(
            False, ("%s %s %s %s %s%s:%s %s ", "%s %s %s %s %s%s:%s %s ", "c-format")
        )

        self.do_test(False, ("%s%s, %s%s (", "%s%s, %s%s (", "c-format"))

        self.do_test(False, ("%s %s Fax: %s", "%s %s Fax: %s", "c-format"))

        self.do_test(False, ("%i C", "%i C", "c-format"))

        self.do_test(False, ("%Ln C", "%Ln C", "qt-format"))
        self.do_test(False, ("%+.2<amount>f C", "%+.2<amount>f C", "ruby-format"))
        self.do_test(False, ("%{amount} C", "%{amount} C", "ruby-format"))

    def test_same_rst(self) -> None:
        self.do_test(False, (":ref:`index`", ":ref:`index`", "rst-text"))
        self.do_test(
            False,
            (
                ":config:option:`$cfg['Servers'][$i]['pmadb']`",
                ":config:option:`$cfg['Servers'][$i]['pmadb']`",
                "rst-text",
            ),
        )
        self.do_test(True, ("See :ref:`index`", "See :ref:`index`", "rst-text"))
        self.do_test(False, ("``mysql``", "``mysql``", "rst-text"))
        self.do_test(True, ("Use ``mysql`` module", "Use ``mysql`` module", "rst-text"))

    def test_same_email(self) -> None:
        self.do_test(False, ("michal@cihar.com", "michal@cihar.com", ""))
        self.do_test(True, ("Write michal@cihar.com", "Write michal@cihar.com", ""))

    def test_same_url(self) -> None:
        self.do_test(False, ("https://weblate.org/", "https://weblate.org/", ""))
        self.do_test(True, ("See https://weblate.org/", "See https://weblate.org/", ""))
        self.do_test(
            False,
            (
                "[2]: http://code.google.com/p/pybluez/",
                "[2]: http://code.google.com/p/pybluez/",
                "",
            ),
        )
        self.do_test(
            False,
            (
                "[2]: https://sourceforge.net/projects/pywin32/",
                "[2]: https://sourceforge.net/projects/pywin32/",
                "",
            ),
        )

    def test_same_channel(self) -> None:
        self.do_test(False, ("#weblate", "#weblate", ""))
        self.do_test(True, ("Please use #weblate", "Please use #weblate", ""))

    def test_same_domain(self) -> None:
        self.do_test(False, ("weblate.org", "weblate.org", ""))
        self.do_test(False, ("demo.weblate.org", "demo.weblate.org", ""))
        self.do_test(
            False, ("#weblate @ irc.freenode.net", "#weblate @ irc.freenode.net", "")
        )
        self.do_test(
            True, ("Please see demo.weblate.org", "Please see demo.weblate.org", "")
        )

    def test_same_path(self) -> None:
        self.do_test(
            False,
            (
                "/cgi-bin/koha/catalogue/search.pl?q=",
                "/cgi-bin/koha/catalogue/search.pl?q=",
                "",
            ),
        )
        self.do_test(True, ("File/path/directory", "File/path/directory", ""))

    def test_same_template(self) -> None:
        self.do_test(
            False, ("{building}: {description}", "{building}: {description}", "")
        )
        self.do_test(False, ("@NAME@: @BOO@", "@NAME@: @BOO@", ""))
        self.do_test(True, ("{building}: summary", "{building}: summary", ""))
        self.do_test(True, ("@NAME@: long text", "@NAME@: long text", ""))

    def test_same_lists(self) -> None:
        self.do_test(False, ("a.,b.,c.,d.", "a.,b.,c.,d.", ""))
        self.do_test(False, ("i.,ii.,iii.,iv.", "i.,ii.,iii.,iv.", ""))

    def test_same_alphabet(self) -> None:
        self.do_test(
            False,
            (
                "!\"#$%%&amp;'()*+,-./0123456789:;&lt;=&gt;?@"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
                "abcdefghijklmnopqrstuvwxyz{|}~",
                "!\"#$%%&amp;'()*+,-./0123456789:;&lt;=&gt;?@"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
                "abcdefghijklmnopqrstuvwxyz{|}~",
                "",
            ),
        )

    def test_same_uppercase(self) -> None:
        self.do_test(False, ("RMS", "RMS", ""))
        self.do_test(False, ("<primary>RMS</primary>", "<primary>RMS</primary>", ""))
        self.do_test(True, ("Who is RMS?", "Who is RMS?", ""))

    def test_same_placeholders(self) -> None:
        self.do_test(True, ("%location%", "%location%", ""))
        self.do_test(False, ("%location%", "%location%.", "placeholders:%location%"))
        self.do_test(
            False,
            ("%SCHOOLING_PERIOD%", "%SCHOOLING_PERIOD%", r'placeholders:r"%\w+%"'),
        )
        self.do_test(
            False,
            (
                "%SCHOOLING_PERIOD%",
                "%SCHOOLING_PERIOD%",
                r'placeholders:r"%\w+%",strict-same',
            ),
        )

    def test_same_project(self) -> None:
        self.do_test(False, ("MockProject", "MockProject", ""))
        self.do_test(False, ("mockcomponent", "mockcomponent", ""))

    def test_same_routine(self) -> None:
        self.do_test(
            False, ("routine 1, routine 2, ...", "routine 1, routine 2, ...", "")
        )
        self.do_test(False, ("routine1, routine2, ...", "routine1, routine2, ...", ""))
        self.do_test(
            True, ("routine_foobar, routine2, ...", "routine_foobar, routine2, ...", "")
        )


class GlossarySameCheckTest(ViewTestCase):
    check = SameCheck()
    CREATE_GLOSSARIES = True

    def setUp(self) -> None:
        super().setUp()
        self.unit = self.get_unit()
        self.unit.translate(self.user, self.unit.source, STATE_TRANSLATED)
        self.unit.check_cache = {}
        self.unit.glossary_terms = None
        del self.unit.__dict__["all_flags"]
        self.glossary = self.project.glossaries[0].translation_set.get(
            language=self.unit.translation.language
        )

    def add_glossary(self, source: str, flags: str) -> None:
        self.glossary.add_unit(None, context="", source=source, extra_flags=flags)

    def add_glossary_words(self, flags: str = "terminology,read-only") -> None:
        self.add_glossary("hello", flags)
        self.add_glossary("world", flags)

    def add_glossary_sentence(self, flags: str = "terminology,read-only") -> None:
        self.add_glossary("Hello, world", flags)

    def test_disabled(self) -> None:
        self.add_glossary_words()
        self.assertFalse(self.check.should_ignore(self.unit.source, self.unit))

    def test_words(self) -> None:
        self.add_glossary_words()
        self.unit.extra_flags = "check-glossary"
        self.assertTrue(self.check.should_ignore(self.unit.source, self.unit))

    def test_translatable_words(self) -> None:
        self.add_glossary_words("terminology")
        self.unit.extra_flags = "check-glossary"
        self.assertFalse(self.check.should_ignore(self.unit.source, self.unit))

    def test_sentence(self) -> None:
        self.add_glossary_sentence()
        self.unit.extra_flags = "check-glossary"
        self.assertTrue(self.check.should_ignore(self.unit.source, self.unit))

    def test_translatable_sentence(self) -> None:
        self.add_glossary_sentence("terminology")
        self.unit.extra_flags = "check-glossary"
        self.assertFalse(self.check.should_ignore(self.unit.source, self.unit))
