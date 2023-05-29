# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Git based version control system abstraction for Weblate needs."""


from lxml import etree

PARSER = etree.XMLParser(strip_cdata=False, resolve_entities=False)


def parse_xml(text):
    """Parse XML without resolving entities."""
    return etree.fromstring(text, PARSER)
