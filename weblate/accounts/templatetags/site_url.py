# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Provide user friendly names for social authentication methods."""

from io import StringIO

from django import template
from django.utils.safestring import mark_safe
from lxml import etree

from weblate.utils.site import get_site_url

register = template.Library()


@register.filter
def add_site_url(content):
    """Automatically add site URL to any relative links or images."""
    parser = etree.HTMLParser(collect_ids=False)
    tree = etree.parse(StringIO(content), parser)  # noqa: S320
    for link in tree.findall(".//a"):
        url = link.get("href")
        if url.startswith("/"):
            link.set("href", get_site_url(url))
    for link in tree.findall(".//img"):
        url = link.get("src")
        if url.startswith("/"):
            link.set("src", get_site_url(url))
    return mark_safe(  # noqa: S308
        etree.tostring(
            tree.getroot(), pretty_print=True, method="html", encoding="unicode"
        )
    )
