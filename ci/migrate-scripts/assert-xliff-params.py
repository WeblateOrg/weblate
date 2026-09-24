# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assertion for XLIFF placeables/whitespace migration."""

from weblate.trans.models import Component

cases = (
    ("xliff-plain", "xliff", "plain"),
    ("xliff2-placeables", "xliff2", "placeables"),
)
for slug, file_format, placeables in cases:
    component = Component.objects.get(slug=slug)
    assert component.file_format == file_format, (slug, component.file_format)
    assert component.file_format_params["xliff_placeables"] == placeables, (
        slug,
        component.file_format_params,
    )
    assert component.file_format_params["xml_whitespace_handling"] == "standard", (
        slug,
        component.file_format_params,
    )
