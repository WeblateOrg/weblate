# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for sitemaps."""

from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.xml import parse_xml


class SitemapTest(FixtureTestCase):
    def test_sitemaps(self) -> None:
        # Get root sitemap
        response = self.client.get("/sitemap.xml")
        self.assertContains(response, "<sitemapindex")

        # Parse it
        tree = parse_xml(response.content)
        sitemaps = tree.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap")
        for sitemap in sitemaps:
            location = sitemap.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            response = self.client.get(location.text)
            self.assertContains(response, "<urlset")
            # Try if it's a valid XML
            parse_xml(response.content)
