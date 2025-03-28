# Copyright © Henry Wilkes <henry@torproject.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import TargetCheck
from weblate.checks.fluent.utils import (
    FluentPatterns,
    FluentUnitConverter,
    format_html_code,
    format_html_error_list,
    translation_from_check,
)

if TYPE_CHECKING:
    from django.utils.safestring import SafeString
    from django_stubs_ext import StrOrPromise
    from translate.storage.fluent import FluentPart

    from weblate.checks.fluent.utils import CheckModel, HighlightsType, TransUnitModel


class _PartsDifference:
    """Represents the missing or extra parts in the target."""

    def __init__(
        self,
        source_parts: list[FluentPart],
        target_parts: list[FluentPart],
    ) -> None:
        # We don't expect any duplicate part names since that should raise a
        # syntax error in the translation toolkit.
        self._missing = [
            part.name
            for part in source_parts
            if not self._has_matching_part(target_parts, part)
        ]
        self._extra = [
            part.name
            for part in target_parts
            if not self._has_matching_part(source_parts, part)
        ]

    @staticmethod
    def _has_matching_part(
        part_list: list[FluentPart],
        find_part: FluentPart,
    ) -> bool:
        return any(part.name == find_part.name for part in part_list)

    def __bool__(self) -> bool:
        return bool(self._missing or self._extra)

    def description(self) -> SafeString:
        errors = []
        if "" in self._missing:
            errors.append(gettext("Fluent value is empty."))
        if "" in self._extra:
            errors.append(gettext("Fluent value should be empty."))
        for part_name in self._missing:
            if not part_name:
                continue
            errors.append(
                format_html_code(
                    gettext("Missing Fluent attribute: {hint}"),
                    hint=f".{part_name}\xa0=\xa0…",
                )
            )
        for part_name in self._extra:
            if not part_name:
                continue
            errors.append(
                format_html_code(
                    gettext("Unexpected Fluent attribute: {hint}"),
                    hint=f".{part_name}\xa0=\xa0…",
                )
            )

        return format_html_error_list(errors)


class FluentPartsCheck(TargetCheck):
    """
    Check that the target has the same Fluent parts as the source.

    Each Fluent Message can have an optional value (the main text content), and
    optional attributes, each of which is a "part" of the Message. In Weblate,
    all these parts appear within the same block, using Fluent-like syntax to
    specify the attributes. For example:

    | This is the Message value
    | .title = This is the title attribute
    | .alt = This is the alt attribute

    This check ensures that the translated Message also has a value if the
    source Message has one, or no value if the source has none. This also checks
    that the same attributes used in the source Message also appear in the
    translation, with no additions.

    NOTE: This check is not applied to Fluent Terms since Terms always have a
    value, and Term attributes tend to be locale-specific (used for grammar
    rules, etc.), and are not expected to appear in all translations.
    """

    check_id = "fluent-parts"
    name = gettext_lazy("Fluent parts")
    description = gettext_lazy("Fluent parts should match.")
    default_disabled = True

    @classmethod
    def _compare_parts(
        cls, unit: TransUnitModel, source: str, target: str
    ) -> _PartsDifference | None:
        """Compare the list of parts found in the source and target."""
        source_unit = FluentUnitConverter(unit, source)
        if source_unit.fluent_type() == "Term":
            # Don't want to check Terms since their attributes are
            # locale-specific and a Term missing a value is a fluent syntax
            # error.
            return None

        source_parts = source_unit.to_fluent_parts()

        if source_parts is None:
            # Some syntax error.
            return None

        target_parts = FluentUnitConverter(unit, target).to_fluent_parts()

        if target_parts is None:
            # Some syntax error, so don't compare.
            return None

        return _PartsDifference(source_parts, target_parts)

    def check_single(
        self,
        source: str,
        target: str,
        unit: TransUnitModel,
    ) -> bool:
        return bool(self._compare_parts(unit, source, target))

    def check_highlight(
        self,
        source: str,
        unit: TransUnitModel,
    ) -> HighlightsType:
        if self.should_skip(unit):
            return []

        # We want to highlight the attribute syntax in Messages.

        fluent_unit = FluentUnitConverter(unit, source)
        if fluent_unit.fluent_type() == "Term":
            return []

        highlight_patterns = []
        for part in fluent_unit.to_fluent_parts() or []:
            if not part.name:
                # Don't highlight the value since there is no visible syntax for
                # it.
                continue
            # We want to match ".attr-name =" at the line start for each
            # attribute.
            # The attribute name shouldn't need escaping, but we do so here for
            # safety.
            highlight_patterns.append(r"^ *\." + re.escape(part.name) + r" *=")
        return FluentPatterns.highlight_source(source, highlight_patterns)

    def get_description(self, check_model: CheckModel) -> StrOrPromise:
        (unit, source, target) = translation_from_check(check_model)
        difference = self._compare_parts(unit, source, target)
        if not difference:
            return super().get_description(check_model)

        return difference.description()
