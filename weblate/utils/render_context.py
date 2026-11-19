# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validate and snapshot application data before template evaluation."""

# Exact types exclude subclasses with application-defined hooks.
# pylint: disable=unidiomatic-typecheck

from __future__ import annotations

import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import cast
from uuid import UUID

from django.utils.translation import gettext

from weblate.utils.render_engine import check_text
from weblate.utils.render_limits import CONTEXT_LIMIT, DEPTH_LIMIT
from weblate.utils.render_policy import TemplateDiagnosticError

type TemplateScalar = str | bool | int | float | datetime | date | time | Decimal | None
type TemplateValue = TemplateScalar | list[TemplateValue] | dict[str, TemplateValue]
type TemplateContext = dict[str, TemplateValue]


class ContextSnapshot:
    def __init__(self) -> None:
        self.remaining = CONTEXT_LIMIT

    def charge(self, size: int) -> None:
        self.remaining -= size
        if self.remaining < 0:
            msg = gettext("Template context exceeds its size limit.")
            raise TemplateDiagnosticError(msg)

    def copy(self, value: object, depth: int = 0) -> TemplateValue:
        if depth > DEPTH_LIMIT:
            msg = gettext("Template context is nested too deeply.")
            raise TemplateDiagnosticError(msg)
        # Charge every occurrence before copying, including shared references.
        self.charge(32)
        if value is None or type(value) is bool:
            return value
        if type(value) is str:
            self.charge(check_text(value, CONTEXT_LIMIT))
            return value
        if type(value) is int:
            # Bound numeric representation before converting it to text in JSON.
            self.charge((value.bit_length() + 2) // 3 + 1)
            return value
        if type(value) is float:
            if not math.isfinite(value):
                msg = gettext("Unsupported nonfinite template context value.")
                raise TemplateDiagnosticError(msg)
            return value
        if type(value) is datetime or type(value) is date or type(value) is time:
            self.charge(len(value.isoformat()))
            return value
        if type(value) is Decimal:
            # Bound coefficient formatting without copying its digits to a tuple.
            # Four times the stored size leaves room for decimal digits and the
            # fixed overhead covers sign, decimal point, and exponent notation.
            if 4 * value.__sizeof__() + 64 > self.remaining:
                msg = gettext("Template context exceeds its size limit.")
                raise TemplateDiagnosticError(msg)
            self.charge(check_text(str(value), CONTEXT_LIMIT))
            return value
        if type(value) is UUID:
            self.charge(36)
            return str(value)
        if type(value) is dict:
            result: TemplateContext = {}
            for key, item in value.items():
                if type(key) is not str:
                    msg = gettext("Unsupported template context key.")
                    raise TemplateDiagnosticError(msg)
                self.charge(check_text(key, CONTEXT_LIMIT) + 8)
                result[key] = self.copy(item, depth + 1)
            return result
        if type(value) is list or type(value) is tuple:
            return [self.copy(item, depth + 1) for item in value]
        msg = gettext("Unsupported template context value.")
        raise TemplateDiagnosticError(msg)


def validate_context(values: dict[str, object]) -> TemplateContext:
    """Copy a complete context, rejecting unsupported types without coercion."""
    if type(values) is not dict:
        msg = gettext("Unsupported template context value.")
        raise TemplateDiagnosticError(msg)
    return cast("TemplateContext", ContextSnapshot().copy(values))
