# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from collections import defaultdict

from six.moves import html_parser


class MarkupExtractor(html_parser.HTMLParser):
    def __init__(self):
        self.found_tags = set()
        self.found_attributes = defaultdict(set)
        html_parser.HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        self.found_tags.add(tag)
        found_attributes = self.found_attributes[tag]
        for attr in attrs:
            found_attributes.add(attr[0])


def extract_bleach(text):
    """Exctract tags from text in a form suitable for bleach"""
    extractor = MarkupExtractor()
    extractor.feed(text)
    return {"tags": extractor.found_tags, "attributes": extractor.found_attributes}
