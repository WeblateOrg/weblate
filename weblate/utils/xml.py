# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Git based version control system abstraction for Weblate needs."""

from functools import lru_cache

from lxml import etree

PARSER = etree.XMLParser(strip_cdata=False, resolve_entities=False)


@lru_cache(maxsize=128)
def parse_xml(text):
    """Parse XML without resolving entities."""
    return etree.fromstring(text, PARSER)  # noqa: S320
