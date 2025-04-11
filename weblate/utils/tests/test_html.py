# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.test import SimpleTestCase

from weblate.checks.flags import Flags
from weblate.utils.html import (
    HTML2Text,
    HTMLSanitizer,
    extract_html_tags,
    list_to_tuples,
    mail_quote_value,
)


class HTMLSanitizerTestCase(SimpleTestCase):
    def sanitize(self, source: str, translation: str, flags: str = "") -> str:
        sanitizer = HTMLSanitizer()
        return sanitizer.clean(source, translation, Flags(flags))

    def test_clean(self) -> None:
        self.assertEqual(self.sanitize("<b>translation</b>", "text"), "translation")

    def test_clean_style(self) -> None:
        self.assertEqual(
            self.sanitize("<style>translation</style>", "<style>text</style>"),
            "<style>translation</style>",
        )


class HtmlTestCase(SimpleTestCase):
    def test_noattr(self) -> None:
        self.assertEqual(extract_html_tags("<b>text</b>"), ({"b"}, {"b": set()}))

    def test_style(self) -> None:
        self.assertEqual(
            extract_html_tags(
                """<style type="text/css"> .style1 { font-family: Arial, Helvetica, sans-serif; } </style>"""
            ),
            ({"style"}, {"style": {"type"}}),
        )

    def test_attrs(self) -> None:
        self.assertEqual(
            extract_html_tags('<a href="#">t</a>'), ({"a"}, {"a": {"href"}})
        )

    def test_noclose(self) -> None:
        self.assertEqual(extract_html_tags("<br>"), ({"br"}, {"br": set()}))

    def test_html2text_simple(self) -> None:
        html2text = HTML2Text()
        self.assertEqual(html2text.handle("<b>text</b>"), "**text**\n\n")

    def test_html2text_img(self) -> None:
        html2text = HTML2Text()
        self.assertEqual(
            html2text.handle("<b>text<img src='text.png' /></b>"), "**text**\n\n"
        )

    def test_html2text_wrap(self) -> None:
        html2text = HTML2Text()
        self.assertEqual(
            html2text.handle("text " * 20),
            """text text text text text text text text text text text text text text text
text text text text text

""",
        )

    def test_html2text_table(self) -> None:
        html2text = HTML2Text()
        self.assertEqual(
            html2text.handle(
                """
<table>
    <tr>
        <td>1</td>
        <td>2</td>
    </tr>
    <tr>
        <td>very long text</td>
        <td>other text</td>
    </tr>
</table>
"""
            ),
            """| 1              | 2          |
|----------------|------------|
| very long text | other text |


""",
        )

    def test_html2text_diff(self) -> None:
        html2text = HTML2Text()
        self.assertEqual(
            html2text.handle("text<ins>add</ins><del>remove</del>"),
            "text{+add+}[-remove-]\n\n",
        )
        self.assertEqual(
            html2text.handle("text <ins>add</ins><del>remove</del>"),
            "text {+add+}[-remove-]\n\n",
        )
        self.assertEqual(
            html2text.handle("text<ins> </ins>"),
            "text{+ +}\n\n",
        )


class MailQuoteTestCase(SimpleTestCase):
    def test_plain(self) -> None:
        self.assertEqual(
            mail_quote_value("text"),
            "text",
        )

    def test_dot(self) -> None:
        self.assertEqual(
            mail_quote_value("example.com"),
            "example<span>.</span>com",
        )

    def test_url(self) -> None:
        self.assertEqual(
            mail_quote_value("https://test.example.com"),
            "https<span>:</span>//test<span>.</span>example<span>.</span>com",
        )


class TypeConversionTestCase(SimpleTestCase):
    def test_list_to_tuples(self) -> None:
        self.assertEqual(
            list_to_tuples(["string1", "string2", "string3"]),
            [("string1",), ("string2",), ("string3",)],
        )

    def test_empty_list(self) -> None:
        self.assertEqual(list_to_tuples([]), [])

    def test_single_element_list(self) -> None:
        self.assertEqual(list_to_tuples(["only_one"]), [("only_one",)])
