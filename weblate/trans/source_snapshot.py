# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Immutable source values shared by dependency processing and its consumers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Self, TypedDict, cast

from weblate.lang.models import Language, Plural
from weblate.trans.util import split_plural
from weblate.utils.terminology import term_records

if TYPE_CHECKING:
    from weblate.trans.models.unit import Unit
    from weblate.utils.terminology import TermRecord


type MissingSourceCache = dict[int, tuple[SourceSnapshot, Language]]


class SourceSnapshotData(TypedDict):
    text: str
    language_id: int
    language_code: str
    language_name: str
    language_direction: str
    plural_id: int
    number: int
    formula: str
    plural_type: int
    terms: list[TermRecord]


@dataclass(frozen=True)
class SourceSnapshot:
    text: str
    language_id: int
    language_code: str
    language_name: str
    language_direction: str
    plural_id: int
    number: int
    formula: str
    plural_type: int
    terms: list[TermRecord] = field(default_factory=list)

    @classmethod
    def from_unit(cls, unit: Unit, *, canonical: bool = False) -> Self:
        if canonical:
            text = unit.source
            language = unit.translation.component.source_language
            plural = (unit.source_unit or unit).translation.plural
        else:
            text = unit.effective_source
            language = unit.effective_source_language
            plural = unit.effective_source_plural
        source = (unit.source_unit or unit) if canonical else unit.effective_source_unit
        terms = (
            term_records(source, source=canonical or source.is_source)
            if source is not None and unit.translation.component.is_multivalue
            else []
        )
        return cls(
            text,
            language.pk,
            language.code,
            language.name,
            language.direction,
            plural.pk,
            plural.number,
            plural.formula,
            plural.type,
            terms,
        )

    @classmethod
    def from_dict(cls, data: SourceSnapshotData) -> Self:
        return cls(**data)

    def as_dict(self) -> SourceSnapshotData:
        return cast("SourceSnapshotData", asdict(self))

    @property
    def language(self) -> Language:
        return Language(
            pk=self.language_id,
            code=self.language_code,
            name=self.language_name,
            direction=self.language_direction,
        )

    @property
    def plural(self) -> Plural:
        return Plural(
            pk=self.plural_id,
            language=self.language,
            number=self.number,
            formula=self.formula,
            type=self.plural_type,
        )

    @property
    def forms(self) -> list[str]:
        return split_plural(self.text)

    @property
    def identity(self) -> tuple[str, int, int, str, int, str]:
        """Source semantics, excluding mutable language display names."""
        return (self.text, *self.rules, json.dumps(self.terms, sort_keys=True))

    @property
    def rules(self) -> tuple[int, int, str, int]:
        return (
            self.language_id,
            self.number,
            self.formula,
            self.plural_type,
        )
