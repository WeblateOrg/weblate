#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Tests for markup quality checks."""


from weblate.checks.markup import (
    BBCodeCheck,
    MarkdownLinkCheck,
    MarkdownRefLinkCheck,
    MarkdownSyntaxCheck,
    SafeHTMLCheck,
    URLCheck,
    XMLTagsCheck,
    XMLValidityCheck,
)
from weblate.checks.tests.test_checks import CheckTestCase
from weblate.trans.models import Unit


class BBCodeCheckTest(CheckTestCase):
    check = BBCodeCheck()

    def setUp(self):
        super().setUp()
        self.test_good_matching = ("[a]string[/a]", "[a]string[/a]", "")
        self.test_failure_1 = ("[a]string[/a]", "[b]string[/b]", "")
        self.test_failure_2 = ("[a]string[/a]", "string", "")
        self.test_highlight = ("", "[a]string[/a]", [(0, 3, "[a]"), (9, 13, "[/a]")])


class XMLValidityCheckTest(CheckTestCase):
    check = XMLValidityCheck()

    def setUp(self):
        super().setUp()
        self.test_good_matching = ("<a>string</a>", "<a>string</a>", "xml-text")
        self.test_good_none = ("string", "string", "")
        self.test_good_ignore = ("<http://weblate.org/>", "<http://weblate.org/>", "")
        self.test_failure_1 = ("<a>string</a>", "<a>string</b>", "xml-text")
        self.test_failure_2 = ("<a>string</a>", "<a>string", "")
        self.test_failure_3 = ("<a>string</a>", "<b>string</a>", "xml-text")

    def test_unicode(self):
        self.do_test(False, ("<a>zkouška</a>", "<a>zkouška</a>", ""))

    def test_not_well_formed(self):
        self.do_test(
            True, ("<emphasis>1st</emphasis>", "<emphasis>not</ emphasis>", "")
        )
        self.do_test(
            True, ("<emphasis>2nd</emphasis>", "<emphasis>not< /emphasis>", "")
        )

    def test_root(self):
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

    def test_html(self):
        self.do_test(False, ("This is<br>valid HTML", "Toto je<br>platne HTML", ""))


class XMLTagsCheckTest(CheckTestCase):
    check = XMLTagsCheck()

    def setUp(self):
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

    def test_unicode(self):
        self.do_test(False, ("<a>zkouška</a>", "<a>zkouška</a>", ""))

    def test_attributes(self):
        self.do_test(False, ('<a href="#">a</a>', '<a href="other">z</a>', ""))
        self.do_test(
            True, ('<a href="#">a</a>', '<a href="#" onclick="alert()">z</a>', "")
        )

    def test_root(self):
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

    def setUp(self):
        super().setUp()
        self.test_good_matching = ("[a][a1]", "[b][a1]", "md-text")
        self.test_good_none = ("string", "string", "md-text")
        self.test_good_flag = ("[a][a1]", "[b][a2]", "")
        self.test_failure_1 = ("[a][a1]", "[b][a2]", "md-text")


class MarkdownLinkCheckTest(CheckTestCase):
    check = MarkdownLinkCheck()

    def setUp(self):
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

    def test_template(self):
        self.do_test(
            False,
            (
                "[translate]({{ site.baseurl }}/docs/Translation/) here",
                "Die [übersetzen]({{ site.baseurl }}/docs/Translation/)",
                "md-text",
            ),
        )

    def test_spacing(self):
        self.do_test(
            True,
            (
                "[My Home Page](http://example.com)",
                "[Moje stránka] (http://example.com)",
                "md-text",
            ),
        )

    def test_fixup(self):
        unit = Unit(
            source="[My Home Page](http://example.com)",
            target="[Moje stránka] (http://example.com)",
        )

        self.assertEqual(self.check.get_fixup(unit), [(r"\] +\(", "](")])

        unit = Unit(
            source="[My Home Page](http://example.com)",
            target="[Moje stránka]",
        )

        self.assertEqual(self.check.get_fixup(unit), None)


class MarkdownLinkCheckMultipleOrderIndependentLinksTest(CheckTestCase):
    check = MarkdownLinkCheck()

    def setUp(self):
        super().setUp()

        self.test_good_matching = (
            "[Weblate](#weblate) has an [example]({{example}}) "
            "for illustrating the useage of [Weblate](#weblate)",
            "Ein [Beispiel]({{example}}) in [Webspät](#weblate) "
            "illustriert die Verwendung von [Webspät](#weblate)",
            "md-text",
        )

        self.test_failure_1 = (
            "[Weblate](#weblate) has an [example]({{example}}) "
            "for illustrating the useage of [Weblate](#weblate)",
            "Ein [Beispiel]({{example}}) in [Webspät](#weblate) "
            "illustriert die Verwendung von [Webspät](#Webspät)",
            "md-text",
        )
        self.test_failure_2 = (
            "[Weblate](#weblate) has an [example]({{example}}) "
            "for illustrating the useage of [Weblate](#weblate)",
            "Ein [Beispiel]({{example}}) in [Webspät](#weblate) "
            "illustriert die Verwendung von Webspät",
            "md-text",
        )


class MarkdownSyntaxCheckTest(CheckTestCase):
    check = MarkdownSyntaxCheck()

    def setUp(self):
        super().setUp()
        self.test_good_matching = ("**string**", "**string**", "md-text")
        self.test_good_none = ("string", "string", "md-text")
        self.test_good_flag = ("**string**", "string", "")
        self.test_failure_1 = ("**string**", "*string*", "md-text")
        self.test_failure_2 = ("~~string~~", "*string*", "md-text")
        self.test_failure_3 = ("_string_", "*string*", "md-text")
        self.test_highlight = (
            "md-text",
            "**string** ~~strike~~ `code`",
            [
                (0, 2, "**"),
                (8, 10, "**"),
                (11, 13, "~~"),
                (19, 21, "~~"),
                (22, 23, "`"),
                (27, 28, "`"),
            ],
        )


class URLCheckTest(CheckTestCase):
    check = URLCheck()

    def setUp(self):
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

    def setUp(self):
        super().setUp()
        safe = '<a href="https://weblate.org/">link</a>'
        self.test_good_matching = (safe, safe, "safe-html")
        self.test_good_none = ("string", "string", "safe-html")
        self.test_good_flag = ("string", "string", "")
        self.test_failure_1 = (safe, '<a href="javascript:foo()">link</a>', "safe-html")
        self.test_failure_2 = (safe, '<a href="#" onclick="x()">link</a>', "safe-html")
        self.test_failure_3 = (safe, '<iframe src="xxx"></iframe>', "safe-html")
