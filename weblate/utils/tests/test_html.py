# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.test import SimpleTestCase

from weblate.checks.flags import Flags
from weblate.utils.html import (
    AUTO_SAFE_HTML_VOID_TAGS,
    MD_LINK,
    HTML2Text,
    HTMLAttribute,
    HTMLSanitizer,
    extract_html_attributes,
    extract_html_tags,
    html_to_mail_text,
    is_auto_safe_html_source,
    iter_markdown_autolinks,
    iter_markdown_code_spans,
    iter_markdown_syntax,
    list_to_tuples,
    mail_quote_value,
    serialize_mdx_void_elements,
)


class MarkdownLinkTest(SimpleTestCase):
    def test_title(self) -> None:
        for title in (
            '"Translation platform"',
            "'Translation platform'",
            "(Translation platform)",
            '"A (translation) platform"',
            '"A \\"translation\\" platform"',
            "(A \\(translation\\) platform)",
        ):
            for destination in ("https://example.com/", "<https://example.com/>"):
                source = f"[Link]({destination} {title})"
                with self.subTest(source=source):
                    match = MD_LINK.fullmatch(source)
                    assert match is not None
                    self.assertEqual(match[3], "https://example.com/")
                    self.assertEqual(match[4], title)


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

    def test_clean_mdx_void_element(self) -> None:
        value = 'Paragraph.<br /><img src="test.png" onerror="alert(1)" />'
        self.assertEqual(
            self.sanitize(
                value,
                'Paragraph.<br /><img src="test.png" />',
                "safe-mdx",
            ),
            'Paragraph.<br /><img src="test.png" />',
        )

    def test_clean_html_void_element(self) -> None:
        self.assertEqual(
            self.sanitize("Paragraph.<br />", "Paragraph.<br />"),
            "Paragraph.<br>",
        )

    def test_serialize_mdx_void_elements(self) -> None:
        for tag in AUTO_SAFE_HTML_VOID_TAGS:
            with self.subTest(tag=tag):
                self.assertEqual(
                    serialize_mdx_void_elements(f'<{tag} title="test">'),
                    f'<{tag} title="test" />',
                )


class MarkdownSyntaxTestCase(SimpleTestCase):
    def test_code_spans(self) -> None:
        text = "`one` ``two ` inner`` ```three\nlines```"
        self.assertEqual(
            [
                (text[span.start : span.end], span.value)
                for span in iter_markdown_code_spans(text)
            ],
            [
                ("`one`", "`"),
                ("``two ` inner``", "``"),
                ("```three\nlines```", "```"),
            ],
        )

    def test_unmatched_code_spans(self) -> None:
        text = "```a` and ``b``"
        self.assertEqual(
            [text[span.start : span.end] for span in iter_markdown_code_spans(text)],
            ["``b``"],
        )

    def test_escaped_code_span(self) -> None:
        text = r"\` `code` {expression} `"
        self.assertEqual(
            [text[span.start : span.end] for span in iter_markdown_code_spans(text)],
            ["`code`"],
        )

    def test_escaped_code_span_closer(self) -> None:
        text = r"`code\`"
        self.assertEqual(
            [text[span.start : span.end] for span in iter_markdown_code_spans(text)],
            [text],
        )

    def test_partially_escaped_code_span(self) -> None:
        text = r"\``{expression}`"
        self.assertEqual(
            [text[span.start : span.end] for span in iter_markdown_code_spans(text)],
            ["`{expression}`"],
        )

    def test_autolinks(self) -> None:
        text = "See <https://example.com/path> and <noreply@example.com>."
        self.assertEqual(
            [text[span.start : span.end] for span in iter_markdown_autolinks(text)],
            ["<https://example.com/path>", "<noreply@example.com>"],
        )

    def test_code_spans_are_opaque(self) -> None:
        text = "**before `*literal*` after**"
        self.assertEqual(
            [syntax.value for syntax in iter_markdown_syntax(text)],
            ["**", "`"],
        )

    def test_code_spans_in_autolinks(self) -> None:
        text = "<https://example.com/`path`>"
        self.assertEqual(
            [syntax.value for syntax in iter_markdown_syntax(text)],
            ["<"],
        )

    def test_incomplete_autolinks(self) -> None:
        text = "<a@b." * 20_000
        self.assertEqual(list(iter_markdown_autolinks(text)), [])
        self.assertEqual(list(iter_markdown_syntax(text)), [])

    def test_incomplete_code_span(self) -> None:
        for length in (400, 800, 1600, 100_000):
            with self.subTest(length=length):
                text = "`" * length + "X"
                self.assertEqual(list(iter_markdown_code_spans(text)), [])
                self.assertEqual(list(iter_markdown_syntax(text)), [])


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

    def test_extract_html_attributes(self) -> None:
        self.assertEqual(
            extract_html_attributes('<a href="#" title="Link">t</a><br class="x">'),
            [
                HTMLAttribute("a", "href", "#"),
                HTMLAttribute("a", "title", "Link"),
                HTMLAttribute("br", "class", "x"),
            ],
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

    def test_mail_text_simple(self) -> None:
        self.assertEqual(html_to_mail_text("<b>text</b>"), "text")
        self.assertEqual(
            html_to_mail_text("<b>text<img src='text.png' alt='image' /></b>"),
            "text",
        )

    def test_mail_text_wrap(self) -> None:
        result = html_to_mail_text(f"<p>{'text ' * 40}</p>")
        self.assertTrue(all(len(line) <= 79 for line in result.splitlines()))
        self.assertEqual(result.replace("\n", " ").split(), ["text"] * 40)

    def test_mail_text_table(self) -> None:
        result = html_to_mail_text(
            "<table><tr><td>1</td><td>2</td></tr>"
            "<tr><td>very long text</td><td>other text</td></tr></table>"
        )
        self.assertIn("very long text", result)
        self.assertIn("other text", result)
        self.assertNotIn("|", result)

    def test_mail_text_wide_table_preserves_headers(self) -> None:
        url = (
            "https://example.com/projects/example/component/search/?q=state:translated"
        )
        result = html_to_mail_text(
            "<table><thead><tr>"
            "<th>Translation</th><th>Added</th><th>Updated</th>"
            "<th>Translated</th><th>Approved</th>"
            "<th>Needs editing</th><th>Unfinished</th>"
            "</tr></thead><tbody><tr>"
            "<td>Czech</td>"
            f"<td><a href='{url}'>2</a></td>"
            "<td>0</td><td>3</td><td>4</td><td>5</td><td>6</td>"
            "</tr></tbody></table>"
        )
        for labeled_value in (
            "Translation: Czech",
            "Added: 2",
            "Updated: 0",
            "Translated: 3",
            "Approved: 4",
            "Needs editing: 5",
            "Unfinished: 6",
        ):
            self.assertIn(labeled_value, result)
        self.assertIn(url, result)
        self.assertNotIn("|", result)
        self.assertNotIn("Translation: Translation", result)

    def test_mail_text_wide_table_colspan_header(self) -> None:
        url = (
            "https://example.com/projects/example/component/search/?q=state:unfinished"
        )
        result = html_to_mail_text(
            "<table><thead><tr><th>Translation</th>"
            "<th colspan='2'>Unfinished strings</th></tr></thead>"
            "<tr><td>Czech</td><td>12</td>"
            f"<td><a href='{url}'>View</a></td></tr></table>"
        )
        self.assertIn("Translation: Czech", result)
        self.assertIn("Unfinished strings: 12", result)
        self.assertIn("Unfinished strings: View", result)
        self.assertIn(url, result)

    def test_mail_text_wide_table_body_colspan(self) -> None:
        output = "subprocess stdout: " + "diagnostic output " * 8
        result = html_to_mail_text(
            "<table><thead><tr><th>Command</th><th>Error</th></tr></thead>"
            "<tbody><tr><td>./run-script</td><td>Execution failed</td></tr>"
            f"<tr><td colspan='2'><pre>{output}</pre></td></tr></tbody></table>"
        )
        self.assertIn("Command: ./run-script", result)
        self.assertIn("Error: Execution failed", result)
        self.assertIn("subprocess stdout:", result)
        self.assertNotIn("Command: subprocess stdout:", result)
        self.assertNotIn("Error: subprocess stdout:", result)

    def test_mail_text_wide_table_body_colspan_advances_column(self) -> None:
        output = "shared diagnostic output " * 6
        result = html_to_mail_text(
            "<table><thead><tr><th>First</th><th>Second</th><th>Third</th>"
            "</tr></thead><tr>"
            f"<td colspan='2'>{output}</td><td>final value</td>"
            "</tr></table>"
        )
        self.assertIn("shared diagnostic output", result)
        self.assertNotIn("First: shared diagnostic output", result)
        self.assertIn("Third: final value", result)

    def test_mail_text_notification(self) -> None:
        url = "https://example.com/projects/example/component/?q=state:translated"
        result = html_to_mail_text(
            "<h1>Alert triggered</h1>"
            "<p>See <a href='https://example.com/docs'>Documentation</a>.</p>"
            "<ul><li>First alert</li><li>Second alert</li></ul>"
            "<h2>Component Information</h2>"
            "<table><tr><td>Translated strings</td>"
            f"<td><a href='{url}'>339</a></td>"
            f"<td><a href='{url}'>75%</a></td></tr></table>"
            "<img src='cid:email-logo.png@cid.weblate.org' alt='Weblate'>"
        )
        self.assertIn("Alert triggered", result)
        self.assertIn("Documentation (https://example.com/docs)", result)
        self.assertIn("First alert", result)
        self.assertIn("Second alert", result)
        self.assertIn("Translated strings", result)
        self.assertIn("Translated strings: 339", result)
        self.assertIn("75%", result)
        self.assertEqual(result.count(f"({url})"), 2)
        self.assertNotIn("# ", result)
        self.assertNotIn("**", result)
        self.assertNotIn("[Documentation]", result)
        self.assertNotIn("|", result)
        self.assertNotIn("cid:email-logo", result)
        self.assertTrue(
            all(len(line) <= 79 or url in line for line in result.splitlines())
        )

    def test_mail_text_url_not_wrapped(self) -> None:
        url = "https://example.com/" + "path/" * 20
        result = html_to_mail_text(f"<p><a href='{url}'>Documentation</a></p>")
        self.assertIn(url, result)

    def test_mail_text_diff(self) -> None:
        self.assertEqual(
            html_to_mail_text("text<ins>add</ins><del>remove</del>"),
            "text{+add+}[-remove-]",
        )
        self.assertEqual(
            html_to_mail_text("text <ins>add</ins><del>remove</del>"),
            "text {+add+}[-remove-]",
        )
        self.assertEqual(html_to_mail_text("text<ins> </ins>"), "text{+ +}")


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
