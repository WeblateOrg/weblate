# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Immutable source values shared by dependency processing and its consumers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from weblate.lang.models import Language, Plural
from weblate.trans.util import split_plural

if TYPE_CHECKING:
    from weblate.trans.models.unit import Unit


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
    def identity(self) -> tuple[str, int, int, int, str, int]:
        """Source semantics, excluding mutable language display names."""
        return (self.text, *self.rules)

    @property
    def rules(self) -> tuple[int, int, int, str, int]:
        return (
            self.language_id,
            self.plural_id,
            self.number,
            self.formula,
            self.plural_type,
        )
