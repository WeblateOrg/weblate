# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase

from weblate.utils.html import HTML2Text, extract_html_tags


class HtmlTestCase(SimpleTestCase):
    def test_noattr(self):
        self.assertEqual(
            extract_html_tags("<b>text</b>"),
            {"tags": {"b"}, "attributes": {"b": set()}},
        )

    def test_attrs(self):
        self.assertEqual(
            extract_html_tags('<a href="#">t</a>'),
            {"tags": {"a"}, "attributes": {"a": {"href"}}},
        )

    def test_noclose(self):
        self.assertEqual(
            extract_html_tags("<br>"), {"tags": {"br"}, "attributes": {"br": set()}}
        )

    def test_html2text_simple(self):
        html2text = HTML2Text()
        self.assertEqual(html2text.handle("<b>text</b>"), "**text**\n\n")

    def test_html2text_img(self):
        html2text = HTML2Text()
        self.assertEqual(
            html2text.handle("<b>text<img src='text.png' /></b>"), "**text**\n\n"
        )

    def test_html2text_wrap(self):
        html2text = HTML2Text()
        self.assertEqual(
            html2text.handle("text " * 20),
            """text text text text text text text text text text text text text text text
text text text text text

""",
        )

    def test_html2text_table(self):
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

    def test_html2text_diff(self):
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
