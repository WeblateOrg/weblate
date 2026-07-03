# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for placeholder quality checks."""

from unittest.mock import patch

from weblate.checks.placeholders import PlaceholderCheck, RegexCheck
from weblate.checks.tests.test_checks import CheckTestCase
from weblate.lang.models import Language
from weblate.trans.tests.factories import make_check, make_unit
from weblate.trans.tests.test_views import FixtureComponentTestCase


def highlight_spans(highlights):
    return [
        (highlight.start, highlight.end, highlight.text) for highlight in highlights
    ]


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
            "placeholders:$URL$:$2$",
        )
        self.test_highlight = ("placeholders:$URL$", "See $URL$", [(4, 9, "$URL$")])

    def do_test(self, expected, data, lang=None) -> None:
        # Skip using check_single as the Check does not use that
        return

    def test_description(self) -> None:
        unit = make_unit(
            source="string $URL$",
            target="string",
            flags="placeholders:$URL$",
        )
        check = make_check(unit, self.check)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following format strings are missing:
            <span class="hlcheck" data-value="$URL$">$URL$</span>
            """,
        )

    def test_regexp(self) -> None:
        unit = make_unit(
            source="string $URL$",
            target="string $FOO$",
            flags=r"""placeholders:r"(\$)([^$]*)(\$)" """,
        )
        check = make_check(unit, self.check)
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
        unit = make_unit(
            source="string {URL} ",
            target="string {URL}",
            flags=r"""placeholders:r"\s?{\w+}\s?" """,
        )
        check = make_check(unit, self.check)
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

    def test_case_insensitive(self) -> None:
        self.assertTrue(
            self.check.check_target(
                ["Hello %WORLD%"],
                ["Ahoj %world%"],
                make_unit(
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
                make_unit(
                    None,
                    "placeholders:%WORLD%,case-insensitive",
                    self.default_lang,
                    "Hello %WORLD%",
                ),
            )
        )

    def test_escaped_markup(self) -> None:
        unit = make_unit(
            None,
            'icu-message-format, placeholders:r"&lt;[a-z/]+&gt;", xml-text',
            self.default_lang,
            "&lt;strong&gt;Not limit the amount of videos&lt;/strong&gt; new users can upload",
        )
        highlights = list(self.check.check_highlight(unit.source, unit))
        self.assertEqual(
            highlight_spans(highlights),
            [
                (0, 14, "&lt;strong&gt;"),
                (44, 59, "&lt;/strong&gt;"),
            ],
        )
        self.assertEqual(highlights[0].kind, "markup")
        self.assertEqual(highlights[0].group, highlights[1].group)
        self.assertEqual(highlights[0].forbidden_text, ("&lt;", "&gt;", "<", ">"))

    def test_overlapping_non_nested(self) -> None:
        # The 2 flags match partially overlapping spans
        # 'python-brace-format' matches {user.name}.
        # "placeholders:r"\$\{\w+" matches ${user.
        unit = make_unit(
            None,
            r'placeholders:r"\$\{\w+":r"\w+\.\w+\}"',
            self.default_lang,
            "nested ${user.name} non-overlapping",
        )
        highlights = list(self.check.check_highlight(unit.source, unit))
        self.assertEqual(
            highlight_spans(highlights),
            [(7, 19, "${user.name}")],
        )
        self.assertEqual(highlights[0].kind, "grammar")

    def test_empty_placeholder_flags_do_not_match(self) -> None:
        for flags in ("placeholders:", 'placeholders:""', 'placeholders:r""'):
            with self.subTest(flags=flags):
                unit = make_unit(source="string", target="translation", flags=flags)
                self.assertFalse(
                    self.check.check_target(["string"], ["translation"], unit)
                )
                self.assertEqual(
                    list(self.check.check_highlight(unit.source, unit)), []
                )

    def test_empty_placeholder_values_are_ignored(self) -> None:
        unit = make_unit(
            source="string $URL$ $2$",
            target="string $URL$",
            flags="placeholders:$URL$:$2$:",
        )
        self.assertTrue(
            self.check.check_target(
                ["string $URL$ $2$"],
                ["string $URL$"],
                unit,
            )
        )
        self.assertEqual(
            highlight_spans(list(self.check.check_highlight(unit.source, unit))),
            [(7, 12, "$URL$"), (13, 16, "$2$")],
        )
        self.assertEqual(
            [
                highlight.kind
                for highlight in self.check.check_highlight(unit.source, unit)
            ],
            ["grammar", "grammar"],
        )

    def test_regexp_timeout(self) -> None:
        unit = make_unit(
            source="string $URL$",
            target="string $URL$",
            flags=r"""placeholders:r"(\$)([^$]*)(\$)" """,
        )
        with (
            patch(
                "weblate.checks.placeholders.regex_finditer",
                side_effect=TimeoutError,
            ),
            patch("weblate.checks.placeholders.report_error"),
        ):
            self.assertFalse(
                self.check.check_target(["string $URL$"], ["string $URL$"], unit)
            )

    def test_highlight_regexp_timeout(self) -> None:
        unit = make_unit(
            source="string $URL$",
            target="string $URL$",
            flags=r"""placeholders:r"(\$)([^$]*)(\$)" """,
        )
        with (
            patch(
                "weblate.checks.placeholders.regex_finditer",
                side_effect=TimeoutError,
            ),
            patch("weblate.checks.placeholders.report_error"),
        ):
            self.assertEqual(list(self.check.check_highlight(unit.source, unit)), [])


class PluralPlaceholdersTest(FixtureComponentTestCase):
    def test_plural(self) -> None:
        check = PlaceholderCheck()
        lang = "cs"
        unit = make_unit(
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
        self.test_highlight = ("regex:URL", "See URL", [])

    def do_test(self, expected, data, lang=None) -> None:
        # Skip using check_single as the Check does not use that
        return

    def test_description(self) -> None:
        unit = make_unit(source="string URL", target="string", flags="regex:URL")
        check = make_check(unit, self.check)
        self.assertEqual(
            self.check.get_description(check),
            "Does not match regular expression <code>URL</code>.",
        )

    def test_check_highlight_groups(self) -> None:
        unit = make_unit(
            None,
            r'regex:"((?:@:\(|\{)[^\)\}]+(?:\)|\}))"',
            self.default_lang,
            "@:(foo.bar.baz) | @:(hello.world) | {foo32}",
        )
        self.assertEqual(list(self.check.check_highlight(unit.source, unit)), [])

    def test_unicode_regex(self) -> None:
        unit = make_unit(
            None,
            r'regex:"((?:@:\(|\{)[-_\p{Lo}\p{Ll}\p{N}]+(?:\)|\}))"',
            self.default_lang,
            "@:(你好世界一۲༣) | @:(Hello-World123) | @:(你好世界一۲༣!) | @:(-你好世界一۲༣_) "
            "| {hello-world123}",
        )
        self.assertEqual(
            list(self.check.check_highlight(unit.source, unit)),
            [],
        )

    def test_regexp_timeout(self) -> None:
        unit = make_unit(
            source="string URL",
            target="string URL",
            flags="regex:URL",
        )
        with (
            patch(
                "weblate.checks.placeholders.regex_findall",
                side_effect=TimeoutError,
            ),
            patch("weblate.checks.placeholders.report_error"),
        ):
            self.assertFalse(
                self.check.check_target(["string URL"], ["string URL"], unit)
            )
