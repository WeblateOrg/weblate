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
    is_auto_safe_html_source,
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

    def test_auto_safe_html_plain_text(self) -> None:
        self.assertTrue(is_auto_safe_html_source("Just text", Flags()))

    def test_auto_safe_html_html(self) -> None:
        self.assertTrue(
            is_auto_safe_html_source('<a href="https://weblate.org">link</a>', Flags())
        )

    def test_auto_safe_html_custom_element(self) -> None:
        self.assertTrue(is_auto_safe_html_source("<x-demo>link</x-demo>", Flags()))

    def test_auto_safe_html_normalized_html(self) -> None:
        for source in (
            "<br/>",
            '<img src="test.png" />',
            "<!-- comment -->",
            "<!DOCTYPE html>",
        ):
            with self.subTest(source=source):
                self.assertTrue(is_auto_safe_html_source(source, Flags()))

    def test_auto_safe_html_inferred_structure(self) -> None:
        self.assertFalse(is_auto_safe_html_source("<option selected>", Flags()))

    def test_auto_safe_html_markdown_autolink(self) -> None:
        self.assertTrue(
            is_auto_safe_html_source("See <https://weblate.org>", Flags("md-text"))
        )

    def test_auto_safe_html_jsx(self) -> None:
        self.assertFalse(
            is_auto_safe_html_source(
                "<TOCInline toc={toc.filter((node)) => node.level === 2)} />",
                Flags("md-text"),
            )
        )

    def test_auto_safe_html_malformed_tag(self) -> None:
        self.assertFalse(is_auto_safe_html_source("<a href=", Flags()))

    def test_auto_safe_html_unmatched_tag_text(self) -> None:
        self.assertFalse(is_auto_safe_html_source("Press <b to continue", Flags()))

    def test_auto_safe_html_quoted_gt(self) -> None:
        self.assertTrue(is_auto_safe_html_source('<a title="1 > 0">link</a>', Flags()))

    def test_auto_safe_html_quoted_lt(self) -> None:
        self.assertTrue(is_auto_safe_html_source('<a title="a<b">link</a>', Flags()))

    def test_auto_safe_html_exotic_markup(self) -> None:
        for source in ("<svg><circle /></svg>", "<math><mrow /></math>"):
            with self.subTest(source=source):
                self.assertFalse(is_auto_safe_html_source(source, Flags()))

    def test_auto_safe_html_duplicate_boolean_attr(self) -> None:
        self.assertFalse(
            is_auto_safe_html_source('<input disabled disabled="">', Flags())
        )

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
            list(list_to_tuples(["string1", "string2", "string3"])),
            [("string1",), ("string2",), ("string3",)],
        )

    def test_empty_list(self) -> None:
        self.assertEqual(list(list_to_tuples([])), [])

    def test_single_element_list(self) -> None:
        self.assertEqual(list(list_to_tuples(["only_one"])), [("only_one",)])
