# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for placeholder quality checks."""

from weblate.checks.flags import Flags
from weblate.checks.models import Check
from weblate.checks.placeholders import PlaceholderCheck, RegexCheck
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit
from weblate.lang.models import Language, Plural
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.trans.tests.test_views import FixtureTestCase


class PlaceholdersTest(CheckTestCase):
    check = PlaceholderCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string $URL$", "string $URL$", "placeholders:$URL$")
        self.test_good_none = ("string", "string", "placeholders:")
        self.test_good_ignore = ("$URL", "$OTHER", "")
        self.test_failure_1 = ("string $URL$", "string", "placeholders:$URL$")
        self.test_failure_2 = ("string $URL$", "string $URL", "placeholders:$URL$")
        self.test_failure_3 = (
            "string $URL$ $2$",
            "string $URL$",
            "placeholders:$URL$:$2$:",
        )
        self.test_highlight = ("placeholders:$URL$", "See $URL$", [(4, 9, "$URL$")])

    def do_test(self, expected, data, lang=None) -> None:
        # Skip using check_single as the Check does not use that
        return

    def test_description(self) -> None:
        unit = Unit(
            source="string $URL$",
            target="string",
            translation=Translation(
                component=Component(
                    project=Project(slug="p", name="p"),
                    source_language=Language(),
                    slug="c",
                    name="c",
                    pk=-1,
                    file_format="po",
                ),
                language=Language(),
                plural=Plural(),
            ),
        )
        unit.__dict__["all_flags"] = Flags("placeholders:$URL$")
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following format strings are missing:
            <span class="hlcheck" data-value="$URL$">$URL$</span>
            """,
        )

    def test_regexp(self) -> None:
        unit = Unit(
            source="string $URL$",
            target="string $FOO$",
            translation=Translation(
                component=Component(
                    project=Project(slug="p", name="p"),
                    source_language=Language(),
                    slug="c",
                    name="c",
                    pk=-1,
                    file_format="po",
                ),
                language=Language(),
                plural=Plural(),
            ),
        )
        unit.__dict__["all_flags"] = Flags(r"""placeholders:r"(\$)([^$]*)(\$)" """)
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following format strings are missing:
            <span class="hlcheck" data-value="$URL$">$URL$</span>
            <br />
            The following format strings are extra:
            <span class="hlcheck" data-value="$FOO$">$FOO$</span>
            """,
        )

    def test_whitespace(self) -> None:
        unit = Unit(
            source="string {URL} ",
            target="string {URL}",
            translation=Translation(
                component=Component(
                    project=Project(slug="p", name="p"),
                    source_language=Language(),
                    slug="c",
                    name="c",
                    pk=-1,
                    file_format="po",
                ),
                language=Language(),
                plural=Plural(),
            ),
        )
        unit.__dict__["all_flags"] = Flags(r"""placeholders:r"\s?{\w+}\s?" """)
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following format strings are missing:
            <span class="hlcheck" data-value=" {URL} ">
            <span class="hlspace"><span class="space-space">
            </span></span>
            {URL}
            <span class="hlspace"><span class="space-space">
            </span></span>
            </span>
            <br />
            The following format strings are extra:
            <span class="hlcheck" data-value=" {URL}">
            <span class="hlspace"><span class="space-space">
            </span></span>
            {URL}
            </span>
            """,
        )

    def test_case_insentivive(self) -> None:
        self.assertTrue(
            self.check.check_target(
                ["Hello %WORLD%"],
                ["Ahoj %world%"],
                MockUnit(
                    None,
                    "placeholders:%WORLD%",
                    self.default_lang,
                    "Hello %WORLD%",
                ),
            )
        )
        self.assertFalse(
            self.check.check_target(
                ["Hello %WORLD%"],
                ["Ahoj %world%"],
                MockUnit(
                    None,
                    "placeholders:%WORLD%,case-insensitive",
                    self.default_lang,
                    "Hello %WORLD%",
                ),
            )
        )


class PluralPlaceholdersTest(FixtureTestCase):
    def test_plural(self) -> None:
        check = PlaceholderCheck()
        lang = "cs"
        unit = MockUnit(
            None,
            'placeholders:r"%[0-9]"',
            lang,
            "1 apple",
        )
        unit.translation.language = Language.objects.get(code=lang)
        unit.translation.plural = unit.translation.language.plural
        self.assertFalse(
            check.check_target(
                ["1 apple", "%1 apples"],
                ["1 jablko", "%1 jablka", "%1 jablek"],
                unit,
            )
        )
        unit.check_cache = {}
        self.assertTrue(
            check.check_target(
                ["1 apple", "%1 apples"],
                ["1 jablko", "1 jablka", "%1 jablek"],
                unit,
            )
        )
        unit.check_cache = {}
        self.assertTrue(
            check.check_target(
                ["%1 apple", "%1 apples"],
                ["1 jablko", "1 jablka", "%1 jablek"],
                unit,
            )
        )


class RegexTest(CheckTestCase):
    check = RegexCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("string URL", "string URL", "regex:URL")
        self.test_good_none = ("string", "string", "regex:")
        self.test_failure_1 = ("string URL", "string", "regex:URL")
        self.test_failure_2 = ("string URL", "string url", "regex:URL")
        self.test_failure_3 = ("string URL", "string URL", "regex:^URL$")
        self.test_highlight = ("regex:URL", "See URL", [(4, 7, "URL")])

    def do_test(self, expected, data, lang=None) -> None:
        # Skip using check_single as the Check does not use that
        return

    def test_description(self) -> None:
        unit = Unit(source="string URL", target="string")
        unit.__dict__["all_flags"] = Flags("regex:URL")
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "Does not match regular expression <code>URL</code>.",
        )

    def test_check_highlight_groups(self) -> None:
        unit = MockUnit(
            None,
            r'regex:"((?:@:\(|\{)[^\)\}]+(?:\)|\}))"',
            self.default_lang,
            "@:(foo.bar.baz) | @:(hello.world) | {foo32}",
        )
        self.assertEqual(
            list(self.check.check_highlight(unit.source, unit)),
            [
                (0, 15, "@:(foo.bar.baz)"),
                (18, 33, "@:(hello.world)"),
                (36, 43, "{foo32}"),
            ],
        )

    def test_unicode_regex(self) -> None:
        unit = MockUnit(
            None,
            r'regex:"((?:@:\(|\{)[-_\p{Lo}\p{Ll}\p{N}]+(?:\)|\}))"',
            self.default_lang,
            "@:(你好世界一۲༣) | @:(Hello-World123) | @:(你好世界一۲༣!) | @:(-你好世界一۲༣_) "
            "| {hello-world123}",
        )
        self.assertEqual(
            list(self.check.check_highlight(unit.source, unit)),
            [
                (0, 11, "@:(你好世界一۲༣)"),
                (50, 63, "@:(-你好世界一۲༣_)"),
                (66, 82, "{hello-world123}"),
            ],
        )
