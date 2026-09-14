# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Metadata for terminology alternatives stored alongside multivalue strings."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from translate.storage.tbx import match_term_indices

from weblate.trans.util import split_plural

if TYPE_CHECKING:
    from weblate.trans.models import Unit


class TermNote(TypedDict):
    text: str
    origin: NotRequired[str | None]
    category: NotRequired[str | None]
    scope: NotRequired[Literal["concept", "language", "term"]]


class TermRecord(TypedDict):
    text: str
    id: str | None
    administrative_status: str | None
    notes: list[TermNote]
    forbidden: NotRequired[bool]


def reconcile_terms(records: list[TermRecord], texts: list[str]) -> list[TermRecord]:
    """Use the same occurrence/text matching as the TBX writer."""
    matches = match_term_indices([record["text"] for record in records], texts)
    result: list[TermRecord] = []
    for text, index in zip(texts, matches, strict=True):
        record: TermRecord = (
            deepcopy(records[index])
            if index is not None
            else {
                "text": text,
                "id": None,
                "administrative_status": None,
                "notes": [],
            }
        )
        record["text"] = text
        result.append(record)
    return result


def term_records(unit: Unit, *, source: bool = False) -> list[TermRecord]:
    """Return records aligned with current, possibly uncommitted string values."""
    side = "source" if source else "target"
    texts = split_plural(unit.source if source else unit.target)
    records = unit.details.get("tbx_terms", {}).get(side, [])
    if not records and not any(texts):
        return []
    return reconcile_terms(records, texts)


def term_forbidden(record: TermRecord) -> bool:
    return (record.get("administrative_status") or "").strip().lower() in {
        "forbidden",
        "obsolete",
        "deprecated",
        "deprecatedtermadmnsts",
        "deprecatedterm-admn-sts",  # codespell:ignore
    }
