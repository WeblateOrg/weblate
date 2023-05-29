# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase

from weblate.utils.html import extract_html_tags


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
