# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

from weblate.formats.ttkit import TBXFormat

if TYPE_CHECKING:
    from weblate.formats.ttkit import TTKitFormat
    from weblate.utils.state import StringState


class BaseFormatFeatures:
    """Base class for format capability attributes (see docs/formats.rst capabilities table)."""

    format: type[TTKitFormat]
    linguality: Literal["bilingual", "mono", "both"] = "mono"
    plurals: bool = False
    descriptions: bool = False
    context: bool = False
    location: bool = False
    flags: bool = False
    additional_states: tuple[StringState, ...] = ()
    additional_features: ClassVar[dict[str, str]] = {}
    read_only_strings: bool = False

    def list_features(self) -> str:
        output = []

        def new_row(*columns: str) -> None:
            output.extend(
                [
                    f"   * - {columns[0]}",
                    *[f"     - {column}" for column in columns[1:]],
                ]
            )

        output.append(".. list-table:: Supported features\n")
        new_row("Identifier", self.format.format_id)
        new_row("Common extensions", ", ".join(self.format.get_class().Extensions))
        new_row("Linguality", self.linguality)

        new_row("Supports descriptions", "Yes" if self.descriptions else "No")
        new_row("Supports context", "Yes" if self.context else "No")
        new_row("Supports location", "Yes" if self.location else "No")
        new_row("Supports flags", "Yes" if self.flags else "No")
        new_row("Supports additional states", "Yes" if self.additional_states else "No")
        new_row("Supports read-only strings", "Yes" if self.read_only_strings else "No")

        for feature, description in self.additional_features.items():
            new_row(feature, description)

        output.append("\n")
        return "\n".join(output)


class TBXFeatures(BaseFormatFeatures):
    format = TBXFormat
    linguality = "bilingual"
    descriptions = True
    context = True
    location = False
    flags = True
    additional_features: ClassVar[dict[str, str]] = {
        ":ref:`format-explanation`": 'Source string explanation is saved and loaded from the ``<descrip>`` tag, translation string explanation from ``<note from="translator">``',
        "Administrative status": 'Terms with administrative status ``forbidden`` or ``obsolete`` in ``<termNote type="administrativeStatus">`` are marked with the ``forbidden`` flag (:ref:`glossary-forbidden`).',
        "Translation needed": 'Terms with ``<termNote type="translationNote">`` containing ``no`` are marked as read-only (:ref:`glossary-untranslatable`).',
        "Usage notes": 'Usage notes from ``<descrip type="Usage note">`` tags are displayed in the glossary.',
    }


FEATURES_REGISTRY = {
    "tbx": TBXFeatures,
}
