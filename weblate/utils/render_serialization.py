# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Native serialization with bounded traversal and temporary expansion."""

# Exact types exclude subclasses with application-defined hooks.
# pylint: disable=unidiomatic-typecheck

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from django.core.serializers.json import DjangoJSONEncoder
from django.utils.translation import gettext

from weblate.utils.render_limits import DEPTH_LIMIT, OUTPUT_LIMIT

if TYPE_CHECKING:
    from weblate.utils.render_engine import RenderBudget


def check_data(value: object, budget: RenderBudget, depth: int = 0) -> None:
    # Loop metadata can add up to one parent per template nesting level.
    if depth > DEPTH_LIMIT * 2:
        budget.reject(
            gettext("Serialized data exceeds the nesting limit of %(limit)d.")
            % {"limit": DEPTH_LIMIT * 2}
        )
    budget.charge(32)
    if type(value) is dict:
        for key, item in value.items():
            check_data(key, budget, depth + 1)
            check_data(item, budget, depth + 1)
    elif type(value) is list or type(value) is tuple:
        for item in value:
            check_data(item, budget, depth + 1)
    else:
        budget.scalar_size(value)


def serialize(value: object, budget: RenderBudget, *, python: bool) -> str:
    check_data(value, budget)
    # A native encoder chunk contains at most one bounded scalar string plus
    # punctuation. Escaping grows UTF-8 data by at most six times. CPython's
    # Unicode representation may use four bytes per output character.
    limit = (
        OUTPUT_LIMIT * 6 + 2
        if python and type(value) not in {list, tuple, dict}
        else OUTPUT_LIMIT
    )
    parts = []
    size = 0
    for part in DjangoJSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(
        value
    ):
        part_size = len(part.encode("utf-8"))
        size += part_size
        if size > limit:
            budget.reject(
                gettext(
                    "Serialization exceeds the intermediate size limit of %(limit)d bytes."
                )
                % {"limit": limit}
            )
        budget.charge(part_size)
        parts.append(part)
    budget.charge(size)
    result = "".join(parts)
    if python:
        budget.charge(size)
        normalized = json.loads(result)
        # repr has at most four ASCII escape characters per source byte;
        # JSON's container punctuation also bounds Python's punctuation.
        result = repr(normalized)
        budget.charge(len(result.encode("utf-8")))
    if len(result.encode("utf-8")) > OUTPUT_LIMIT:
        budget.reject(
            gettext("Serialized value exceeds the size limit of %(limit)d bytes.")
            % {"limit": OUTPUT_LIMIT}
        )
    return result
