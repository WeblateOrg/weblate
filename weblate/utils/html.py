# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from collections import defaultdict

from lxml.etree import HTMLParser

IGNORE = {"body", "html"}


class MarkupExtractor:
    def __init__(self):
        self.found_tags = set()
        self.found_attributes = defaultdict(set)

    def start(self, tag, attrs):
        if tag in IGNORE:
            return
        self.found_tags.add(tag)
        self.found_attributes[tag].update(attrs.keys())


def extract_html_tags(text):
    """Extract tags from text in a form suitable for HTML sanitization."""
    extractor = MarkupExtractor()
    parser = HTMLParser(collect_ids=False, target=extractor)
    parser.feed(text)
    return {"tags": extractor.found_tags, "attributes": extractor.found_attributes}
