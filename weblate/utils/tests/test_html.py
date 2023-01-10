# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase

from weblate.utils.html import extract_bleach


class HtmlTestCase(SimpleTestCase):
    def test_noattr(self):
        self.assertEqual(
            extract_bleach("<b>text</b>"), {"tags": {"b"}, "attributes": {"b": set()}}
        )

    def test_attrs(self):
        self.assertEqual(
            extract_bleach('<a href="#">t</a>'),
            {"tags": {"a"}, "attributes": {"a": {"href"}}},
        )

    def test_noclose(self):
        self.assertEqual(
            extract_bleach("<br>"), {"tags": {"br"}, "attributes": {"br": set()}}
        )
