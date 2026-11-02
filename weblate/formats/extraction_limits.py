# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resource limits for compressed translation format parsing."""

from __future__ import annotations

from translate.storage.extraction_limits import ExtractionBudget

MAX_EXTRACTED_BYTES = 16 * 1024 * 1024
MAX_XML_ELEMENTS = 50_000
MAX_EXTRACTED_UNITS = 20_000


def make_extraction_budget() -> ExtractionBudget:
    """Return a fresh budget for one ODF or IDML archive."""
    return ExtractionBudget(
        max_xml_bytes=MAX_EXTRACTED_BYTES,
        max_elements=MAX_XML_ELEMENTS,
        max_units=MAX_EXTRACTED_UNITS,
    )
