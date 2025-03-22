# Copyright © Henry Wilkes <henry@torproject.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.html import escape
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import SourceCheck, TargetCheck
from weblate.checks.fluent.utils import FluentUnitConverter, translation_from_check

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from weblate.checks.fluent.utils import CheckModel, TransUnitModel


class _FluentSyntaxCheck:
    @staticmethod
    def check_fluent_syntax(source: str, unit: TransUnitModel) -> bool:
        syntax_error = FluentUnitConverter(unit, source).get_syntax_error()
        return bool(syntax_error)

    @staticmethod
    def get_fluent_syntax_error_description(
        check_model: CheckModel, use_source: bool
    ) -> str | None:
        unit, source, target = translation_from_check(check_model)
        if not use_source:  # A target check.
            source = target
        syntax_error = FluentUnitConverter(unit, source).get_syntax_error()
        if not syntax_error:
            return None
        return escape(
            gettext("Fluent syntax error: {error}.").format(error=syntax_error)
        )


class FluentSourceSyntaxCheck(_FluentSyntaxCheck, SourceCheck):
    """Check that the source uses valid Fluent syntax."""

    check_id = "fluent-source-syntax"
    name = gettext_lazy("Fluent source syntax")
    description = gettext_lazy("Fluent syntax error in the source.")
    default_disabled = True

    def check_source_unit(self, source: list[str], unit: TransUnitModel) -> bool:
        return self.check_fluent_syntax(source[0], unit)

    def get_description(self, check_model: CheckModel) -> StrOrPromise:
        return self.get_fluent_syntax_error_description(
            check_model, True
        ) or super().get_description(check_model)


class FluentTargetSyntaxCheck(_FluentSyntaxCheck, TargetCheck):
    """Check that the target uses valid Fluent syntax."""

    check_id = "fluent-target-syntax"
    name = gettext_lazy("Fluent translation syntax")
    description = gettext_lazy("Fluent syntax error in the translation.")
    default_disabled = True

    def check_single(
        self,
        source: str,
        target: str,
        unit: TransUnitModel,
    ) -> bool:
        return self.check_fluent_syntax(target, unit)

    def get_description(self, check_model: CheckModel) -> StrOrPromise:
        return self.get_fluent_syntax_error_description(
            check_model, False
        ) or super().get_description(check_model)
