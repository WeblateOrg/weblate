# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for markup quality checks."""

from __future__ import annotations

from weblate.checks.markup import (
    BBCodeCheck,
    MarkdownLinkCheck,
    MarkdownRefLinkCheck,
    MarkdownSyntaxCheck,
    RSTReferencesCheck,
    RSTSyntaxCheck,
    SafeHTMLCheck,
    URLCheck,
    XMLTagsCheck,
    XMLValidityCheck,
)
from weblate.checks.models import Check
from weblate.checks.tests.test_checks import CheckTestCase
from weblate.lang.models import Language, Plural
from weblate.trans.models import Component, Translation, Unit


class BBCodeCheckTest(CheckTestCase):
    check = BBCodeCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("[a]string[/a]", "[a]string[/a]", "")
        self.test_failure_1 = ("[a]string[/a]", "[b]string[/b]", "")
        self.test_failure_2 = ("[a]string[/a]", "string", "")
        self.test_highlight = ("", "[a]string[/a]", [(0, 3, "[a]"), (9, 13, "[/a]")])


class XMLValidityCheckTest(CheckTestCase):
    check = XMLValidityCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("<a>string</a>", "<a>string</a>", "xml-text")
        self.test_good_none = ("string", "string", "")
        self.test_good_ignore = ("<http://weblate.org/>", "<http://weblate.org/>", "")
        self.test_failure_1 = ("<a>string</a>", "<a>string</b>", "xml-text")
        self.test_failure_2 = ("<a>string</a>", "<a>string", "")
        self.test_failure_3 = ("<a>string</a>", "<b>string</a>", "xml-text")

    def test_unicode(self) -> None:
        self.do_test(False, ("<a>zkouška</a>", "<a>zkouška</a>", ""))

    def test_not_well_formed(self) -> None:
        self.do_test(
            True, ("<emphasis>1st</emphasis>", "<emphasis>not</ emphasis>", "")
        )
        self.do_test(
            True, ("<emphasis>2nd</emphasis>", "<emphasis>not< /emphasis>", "")
        )

    def test_safe_html(self) -> None:
        self.do_test(True, ("<br />", "<br>", ""))
        self.do_test(False, ("<br />", "<br>", "safe-html"))

    def test_root(self) -> None:
        self.do_test(
            False,
            (
                '<?xml version="1.0" encoding="UTF-8"?><b>test</b>',
                '<?xml version="1.0" encoding="UTF-8"?><b>test</b>',
                "",
            ),
        )
        self.do_test(
            True,
            (
                '<?xml version="1.0" encoding="UTF-8"?><b>test</b>',
                '<?xml version="1.0" encoding="UTF-8"?><b>test',
                "",
            ),
        )

    def test_html(self) -> None:
        self.do_test(False, ("This is<br>valid HTML", "Toto je<br>platne HTML", ""))

    def test_skip_mixed(self) -> None:
        self.do_test(
            False,
            (
                ["<emphasis>1st</emphasis>", "<invalid>"],
                "<emphasis>not</ emphasis>",
                "",
            ),
        )

    def test_nonxml(self) -> None:
        self.do_test(False, ("Source", "<<target>>", ""))


class XMLTagsCheckTest(CheckTestCase):
    check = XMLTagsCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("<a>string</a>", "<a>string</a>", "")
        self.test_failure_1 = ("<a>string</a>", "<b>string</b>", "")
        self.test_failure_2 = ("<a>string</a>", "string", "")
        self.test_highlight = (
            "",
            '<b><a href="foo&lt;">bar&copy;</a></b>',
            [
                (0, 3, "<b>"),
                (3, 21, '<a href="foo&lt;">'),
                (30, 34, "</a>"),
                (34, 38, "</b>"),
                (24, 30, "&copy;"),
            ],
        )

    def test_unicode(self) -> None:
        self.do_test(False, ("<a>zkouška</a>", "<a>zkouška</a>", ""))

    def test_attributes(self) -> None:
        self.do_test(False, ('<a href="#">a</a>', '<a href="other">z</a>', ""))
        self.do_test(
            True, ('<a href="#">a</a>', '<a href="#" onclick="alert()">z</a>', "")
        )

    def test_root(self) -> None:
        self.do_test(
            False,
            (
                '<?xml version="1.0" encoding="UTF-8"?><b>test</b>',
                '<?xml version="1.0" encoding="UTF-8"?><b>test</b>',
                "",
            ),
        )
        self.do_test(
            True,
            (
                '<?xml version="1.0" encoding="UTF-8"?><b>test</b>',
                '<?xml version="1.0" encoding="UTF-8"?><a>test</a>',
                "",
            ),
        )


class MarkdownRefLinkCheckTest(CheckTestCase):
    check = MarkdownRefLinkCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("[a][a1]", "[b][a1]", "md-text")
        self.test_good_none = ("string", "string", "md-text")
        self.test_good_flag = ("[a][a1]", "[b][a2]", "")
        self.test_failure_1 = ("[a][a1]", "[b][a2]", "md-text")


class MarkdownLinkCheckTest(CheckTestCase):
    check = MarkdownLinkCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = (
            "[Use Weblate](https://weblate.org/)",
            "[Použij Weblate](https://weblate.org/)",
            "md-text",
        )
        self.test_good_none = ("string", "string", "md-text")
        self.test_failure_1 = (
            "[Use Weblate](https://weblate.org/)",
            "[Použij Weblate]",
            "md-text",
        )
        self.test_failure_2 = (
            "[Use Weblate](https://weblate.org/)",
            "[Použij Weblate] (https://weblate.org/)",
            "md-text",
        )
        self.test_failure_3 = (
            "[Use Weblate](../demo/)",
            "[Použij Weblate](https://example.com/)",
            "md-text",
        )

    def test_template(self) -> None:
        self.do_test(
            False,
            (
                "[translate]({{ site.baseurl }}/docs/Translation/) here",
                "Die [übersetzen]({{ site.baseurl }}/docs/Translation/)",
                "md-text",
            ),
        )

    def test_spacing(self) -> None:
        self.do_test(
            True,
            (
                "[My Home Page](http://example.com)",
                "[Moje stránka] (http://example.com)",
                "md-text",
            ),
        )

    def test_fixup(self) -> None:
        unit = Unit(
            source="[My Home Page](http://example.com)",
            target="[Moje stránka] (http://example.com)",
        )

        self.assertEqual(self.check.get_fixup(unit), [(r"\] +\(", "](")])

        unit = Unit(
            source="[My Home Page](http://example.com)",
            target="[Moje stránka]",
        )

        self.assertIsNone(self.check.get_fixup(unit))

    def test_mutliple_ordered(self) -> None:
        self.do_test(
            False,
            (
                "[Weblate](#weblate) has an [example]({{example}}) "
                "for illustrating the usage of [Weblate](#weblate)",
                "Ein [Beispiel]({{example}}) in [Webspät](#weblate) "
                "illustriert die Verwendung von [Webspät](#weblate)",
                "md-text",
            ),
        )

        self.do_test(
            True,
            (
                "[Weblate](#weblate) has an [example]({{example}}) "
                "for illustrating the usage of [Weblate](#weblate)",
                "Ein [Beispiel]({{example}}) in [Webspät](#weblate) "
                "illustriert die Verwendung von [Webspät](#Webspät)",
                "md-text",
            ),
        )
        self.do_test(
            True,
            (
                "[Weblate](#weblate) has an [example]({{example}}) "
                "for illustrating the usage of [Weblate](#weblate)",
                "Ein [Beispiel]({{example}}) in [Webspät](#weblate) "
                "illustriert die Verwendung von Webspät",
                "md-text",
            ),
        )

    def test_url(self) -> None:
        self.do_test(
            False,
            (
                "See <https://weblate.org/>",
                "Viz <https://weblate.org/>",
                "md-text",
            ),
        )
        self.do_test(
            True,
            (
                "See <https://weblate.org/>",
                "Viz <https:>",
                "md-text",
            ),
        )

    def test_email(self) -> None:
        self.do_test(
            False,
            (
                "See <noreply@weblate.org>",
                "Viz <noreply@weblate.org>",
                "md-text",
            ),
        )
        self.do_test(
            True,
            (
                "See <noreply@weblate.org>",
                "Viz <noreply>",
                "md-text",
            ),
        )


class MarkdownSyntaxCheckTest(CheckTestCase):
    check = MarkdownSyntaxCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = ("**string**", "**string**", "md-text")
        self.test_good_none = ("string", "string", "md-text")
        self.test_good_flag = ("**string**", "string", "")
        self.test_failure_1 = ("**string**", "*string*", "md-text")
        self.test_failure_2 = ("~~string~~", "*string*", "md-text")
        self.test_failure_3 = ("_string_", "*string*", "md-text")
        self.test_highlight = (
            "md-text",
            "**string** ~~strike~~ `code` <https://weblate.org> <noreply@weblate.org>",
            [
                (0, 2, "**"),
                (8, 10, "**"),
                (11, 13, "~~"),
                (19, 21, "~~"),
                (22, 23, "`"),
                (27, 28, "`"),
                (29, 30, "<"),
                (49, 50, ">"),
                (51, 52, "<"),
                (71, 72, ">"),
            ],
        )


class URLCheckTest(CheckTestCase):
    check = URLCheck()

    def setUp(self) -> None:
        super().setUp()
        url = "https://weblate.org/"
        self.test_good_matching = (url, url, "url")
        self.test_good_none = (url, url, "url")
        self.test_good_flag = ("string", "string", "")
        self.test_failure_1 = (url, "https:weblate.org/", "url")
        self.test_failure_2 = (url, "weblate.org/", "url")
        self.test_failure_3 = (url, "weblate", "url")


class SafeHTMLCheckTest(CheckTestCase):
    check = SafeHTMLCheck()

    def setUp(self) -> None:
        super().setUp()
        safe = '<a href="https://weblate.org/">link</a>'
        self.test_good_matching = (safe, safe, "safe-html")
        self.test_good_none = ("string", "string", "safe-html")
        self.test_good_flag = ("string", "string", "")
        self.test_failure_1 = (safe, '<a href="javascript:foo()">link</a>', "safe-html")
        self.test_failure_2 = (safe, '<a href="#" onclick="x()">link</a>', "safe-html")
        self.test_failure_3 = (safe, '<iframe src="xxx"></iframe>', "safe-html")

    def test_markdown(self) -> None:
        self.do_test(
            False,
            (
                "See <https://weblate.org>",
                "Viz <https://weblate.org>",
                "md-text,safe-html",
            ),
        )
        self.do_test(
            True,
            (
                "See <https://weblate.org>",
                "Viz <https://weblate.org>",
                "safe-html",
            ),
        )
        self.do_test(
            False,
            (
                "See <noreply@weblate.org>",
                "Viz <noreply@weblate.org>",
                "md-text,safe-html",
            ),
        )
        self.do_test(
            True,
            (
                "See <noreply@weblate.org>",
                "Viz <noreply@weblate.org>",
                "safe-html",
            ),
        )


class RSTReferencesCheckTest(CheckTestCase):
    check = RSTReferencesCheck()

    def setUp(self) -> None:
        super().setUp()
        base = ":ref:`foo`"
        self.test_good_matching = (base, base, "rst-text")
        self.test_good_none = (base, base, "")
        self.test_good_flag = ("string", "string", "rst-text")
        self.test_failure_1 = (base, ":ref:`bar`", "rst-text")
        self.test_failure_2 = (base, ":doc:`foo`", "rst-text")
        self.test_failure_3 = (base, ":ref:`foo <bar>`", "rst-text")
        self.test_highlight = (
            "rst-text",
            ":ref:`bar` is :doc:`foo <baz>`",
            [(0, 10, ":ref:`bar`"), (14, 30, ":doc:`foo <baz>`")],
        )

    def test_description(self) -> None:
        unit = Unit(
            source=":ref:`bar` `baz`_",
            target=":ref:`bar <baz>` `baz`",
            extra_flags="rst-text",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language(code="en"),
                ),
                plural=Plural(),
            ),
        )
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following format strings are missing:
            <span class="hlcheck" data-value=":ref:`bar`">:ref:`bar`</span>
            <br />
            The following format strings are extra:
            <span class="hlcheck" data-value=":ref:`bar &lt;baz&gt;`">:ref:`bar &lt;baz&gt;`</span>
            <br>
            The following errors were found:
            <br>
            Inconsistent links in the translated message.
            """,
        )

    def test_roles(self) -> None:
        self.do_test(
            False,
            (
                ":guilabel:`Help`",
                ":guilabel:`Pomoc`",
                "rst-text",
            ),
        )
        self.do_test(
            False,
            (
                ":index:`bilingual <pair: translation; bilingual>`",
                ":index:`vícejazyčný <pair: překlad; vícejazyčný>`",
                "rst-text",
            ),
        )
        self.do_test(
            True,
            (
                ":index:`bilingual <pair: translation; bilingual>`",
                ":ndex:`vícejazyčný <pair: překlad; vícejazyčný>`",
                "rst-text",
            ),
        )

    def test_option_space(self) -> None:
        self.do_test(
            True,
            (
                ":option:`wlc push`",
                ":option:`wlc pull`",
                "rst-text",
            ),
        )

    def test_ref_space(self) -> None:
        self.do_test(
            True,
            (
                "Add it to :setting:`django:INSTALLED_APPS`:",
                "把它添加到:setting:`django:INSTALLED_APPS`:",
                "rst-text",
            ),
        )
        self.do_test(
            False,
            (
                "Add it to :setting:`django:INSTALLED_APPS`:",
                "把它添加到 :setting:`django:INSTALLED_APPS`:",
                "rst-text",
            ),
        )
        self.do_test(
            True,
            (
                ":ref:`Searching` now supports",
                ":ref:`Searching`agora suporta",
                "rst-text",
            ),
        )

    def test_translatable(self) -> None:
        self.do_test(
            True,
            (
                ":kbd:`Ctrl+Home`",
                ": kbd:`Ctrl+Home`",
                "rst-text",
            ),
        )
        self.do_test(
            False,
            (
                ":kbd:`Ctrl+Home`",
                ":kbd:`Ctrl+Home`",
                "rst-text",
            ),
        )
        self.do_test(
            False,
            (
                ":kbd:`Ctrl+Home`",
                ":kbd:`Ctrl+Inicio`",
                "rst-text",
            ),
        )
        self.do_test(
            True,
            (
                ":kbd:`Ctrl+Home`",
                ":kbd:`Ctrl+Inicio `",
                "rst-text",
            ),
        )

    def test_footnotes(self) -> None:
        self.do_test(
            True,
            (
                "Context [#c]_",
                "Kontext",
                "rst-text",
            ),
        )
        self.do_test(
            False,
            (
                "Context [#c]_",
                "Kontext [#c]_",
                "rst-text",
            ),
        )

    def test_links(self) -> None:
        self.do_test(
            True,
            (
                "Context `c`_",
                "Kontext",
                "rst-text",
            ),
        )
        # Missing underscore
        self.do_test(
            True,
            (
                "Context `c`_",
                "Kontext `c`",
                "rst-text",
            ),
        )
        self.do_test(
            False,
            (
                "Context `c`_",
                "Kontext `c`_",
                "rst-text",
            ),
        )


class RSTSyntaxCheckTest(CheckTestCase):
    check = RSTSyntaxCheck()

    def setUp(self) -> None:
        super().setUp()
        base = "``foo``"
        self.test_good_matching = (base, base, "rst-text")
        self.test_good_none = (base, base, "")
        self.test_good_flag = ("string", "string", "rst-text")
        self.test_failure_1 = (base, "``foo`", "rst-text")
        self.test_failure_2 = (base, ":ref:`foo`bar", "rst-text")
        self.test_failure_3 = (base, ":ref:`foo bar` `", "rst-text")

    def test_roles(self) -> None:
        self.do_test(
            False,
            (
                ":abcde:`Ctrl+Home`",
                ":abcde:`Ctrl+Home`",
                "rst-text",
            ),
        )
        self.do_test(
            True,
            (
                ":abcde:`Ctrl+Home`",
                ":defgh:`Ctrl+Home`",
                "rst-text",
            ),
        )
        self.do_test(
            True,
            (
                "`Webhooks in Gitea manual <https://docs.gitea.io/en-us/webhooks/>`_",
                "`Webhooks în manualul Gitea <https://docs.gitea.io/en-us/webhooks/>``_",
                "rst-text",
            ),
        )
        self.do_test(
            False,
            (
                "`Webhooks in Gitea manual <https://docs.gitea.io/en-us/webhooks/>`_",
                "`Webhooks in Gitea manual <https://docs.gitea.io/en-us/webhooks/>`_",
                "rst-text",
            ),
        )
        self.do_test(
            False,
            (
                "`Webhooks in Gitea manual`_",
                "`Webhooks in Gitea manual`_",
                "rst-text",
            ),
        )

    def test_description(self) -> None:
        unit = Unit(
            source=":ref:`bar`",
            target=":ref:`bar",
            extra_flags="rst-text",
            translation=Translation(
                component=Component(
                    file_format="po",
                    source_language=Language(code="en"),
                ),
                plural=Plural(),
            ),
        )
        check = Check(unit=unit)
        self.assertHTMLEqual(
            self.check.get_description(check),
            """
            The following errors were found:<br>
            Inline interpreted text or phrase reference start-string without end-string.
            """,
        )
