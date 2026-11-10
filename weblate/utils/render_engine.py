# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Restricted template engine with bounded intermediate values and loop work."""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from datetime import date, datetime, time
from decimal import Decimal
from functools import wraps
from itertools import islice
from time import monotonic
from typing import TYPE_CHECKING, Any, ClassVar, Never, cast
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from django.template import Context, Engine, Library, Template, TemplateSyntaxError
from django.template.base import NodeList
from django.template.defaulttags import ForNode, IfNode
from django.utils.functional import Promise
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from weblate.utils.render_worker import (
    CONTEXT_LIMIT,
    DEPTH_LIMIT,
    LOOP_LIMIT,
    OUTPUT_LIMIT,
    RENDER_TIMEOUT,
    SOURCE_LIMIT,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.template.base import FilterExpression
    from django.utils.safestring import SafeString


def check_text(value: str, limit: int = OUTPUT_LIMIT) -> int:
    if len(value) > limit:
        msg = gettext("Template value exceeds its size limit.")
        raise TemplateSyntaxError(msg)
    size = len(value.encode("utf-8"))
    if size > limit:
        msg = gettext("Template value exceeds its size limit.")
        raise TemplateSyntaxError(msg)
    return size


def encode_value(
    value: object, depth: int = 0, *, remaining: list[int] | None = None
) -> list[Any]:
    """Preserve scalar types without sending executable Python objects."""
    if depth > DEPTH_LIMIT:
        msg = gettext("Template context is nested too deeply.")
        raise TemplateSyntaxError(msg)
    if remaining is None:
        remaining = [CONTEXT_LIMIT]
    # Charge every node, including shared references, before allocating its copy.
    remaining[0] -= 32
    if isinstance(value, Promise):
        value = str(value)
    if isinstance(value, str):
        remaining[0] -= check_text(value, CONTEXT_LIMIT)
    if remaining[0] < 0:
        msg = gettext("Template context exceeds its size limit.")
        raise TemplateSyntaxError(msg)
    if value is None or isinstance(value, str | bool | int | float):
        return ["value", value]
    if isinstance(value, datetime):
        return ["datetime", value.isoformat()]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, time):
        return ["time", value.isoformat()]
    if isinstance(value, Decimal):
        return ["decimal", str(value)]
    if isinstance(value, UUID):
        return ["value", str(value)]
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            if not isinstance(key, str):
                msg = gettext("Unsupported template context key.")
                raise TemplateSyntaxError(msg)
            remaining[0] -= check_text(key, CONTEXT_LIMIT) + 8
            items.append([key, encode_value(item, depth + 1, remaining=remaining)])
        return ["dict", items]
    if isinstance(value, list | tuple):
        return [
            "list",
            [encode_value(item, depth + 1, remaining=remaining) for item in value],
        ]
    msg = gettext("Unsupported template context value.")
    raise TemplateSyntaxError(msg)


def decode_value(value: list[Any], depth: int = 0) -> Any:  # ruff: ignore[any-type]
    if depth > DEPTH_LIMIT:
        msg = gettext("Template context is nested too deeply.")
        raise TemplateSyntaxError(msg)
    kind, data = value
    if kind == "value":
        return data
    if kind == "dict":
        return {key: decode_value(item, depth + 1) for key, item in data}
    if kind == "list":
        return [decode_value(item, depth + 1) for item in data]
    parsers = {
        "datetime": datetime.fromisoformat,
        "date": date.fromisoformat,
        "time": time.fromisoformat,
        "decimal": Decimal,
    }
    return parsers[kind](data)


def encode_request(value: object) -> bytes:
    """Bound serialized context without allocating an unbounded JSON string."""
    output = bytearray()
    for part in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(value):
        if len(part) > CONTEXT_LIMIT:
            msg = gettext("Template context exceeds its size limit.")
            raise TemplateSyntaxError(msg)
        output.extend(part.encode("utf-8"))
        if len(output) > CONTEXT_LIMIT:
            msg = gettext("Template context exceeds its size limit.")
            raise TemplateSyntaxError(msg)
    return bytes(output)


class RenderBudget:
    def __init__(self) -> None:
        self.iterations = 0
        self.deadline = monotonic() + RENDER_TIMEOUT

    def check(self) -> None:
        if monotonic() >= self.deadline:
            msg = gettext("Template rendering exceeded its time limit.")
            raise TemplateSyntaxError(msg)

    def iteration(self) -> None:
        self.check()
        self.iterations += 1
        if self.iterations > LOOP_LIMIT:
            msg = gettext("Template rendering exceeded its loop limit.")
            raise TemplateSyntaxError(msg)


_budget: ContextVar[RenderBudget] = ContextVar("template_render_budget")


class OutputBuffer:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.size = 0

    def append(self, value: str) -> None:
        _budget.get().check()
        self.size += check_text(value)
        if self.size > OUTPUT_LIMIT:
            msg = gettext("Template output exceeds its size limit.")
            raise TemplateSyntaxError(msg)
        self.parts.append(value)

    def render(self) -> SafeString:
        # Django's NodeList contract; render_template removes this internal marker.
        return mark_safe("".join(self.parts))  # ruff: ignore[suspicious-mark-safe-usage]


class BoundedNodeList(NodeList):
    def render(self, context: Context) -> SafeString:
        output = OutputBuffer()
        for node in self:
            output.append(cast("str", node.render_annotated(context)))
        return output.render()


class BoundedForNode(ForNode):
    sequence: FilterExpression
    nodelist_loop: NodeList
    nodelist_empty: NodeList

    def render(self, context: Context) -> str:
        budget = _budget.get()
        parentloop = context.get("forloop", {})
        with context.push():
            values = self.sequence.resolve(context, ignore_failures=True)
            if values is None:
                values = []
            if not hasattr(values, "__len__"):
                values = list(islice(values, LOOP_LIMIT - budget.iterations + 1))
            count = len(values)
            if count > LOOP_LIMIT - budget.iterations:
                msg = gettext("Template rendering exceeded its loop limit.")
                raise TemplateSyntaxError(msg)
            if not count:
                return self.nodelist_empty.render(context)
            if self.is_reversed:
                values = reversed(values)
            loop = context["forloop"] = {"parentloop": parentloop, "length": count}
            output = OutputBuffer()
            for index, item in enumerate(values):
                budget.iteration()
                loop.update(
                    counter0=index,
                    counter=index + 1,
                    revcounter=count - index,
                    revcounter0=count - index - 1,
                    first=index == 0,
                    last=index == count - 1,
                )
                if len(self.loopvars) > 1:
                    try:
                        size = len(item)
                    except TypeError:
                        size = 1
                    if size != len(self.loopvars):
                        msg = "Loop value cannot be unpacked into its variables."
                        raise ValueError(msg)
                    with context.push(dict(zip(self.loopvars, item, strict=True))):
                        output.append(self.nodelist_loop.render(context))
                else:
                    context[self.loopvars[0]] = item
                    output.append(self.nodelist_loop.render(context))
            return output.render()


def bound_nodes(nodes: NodeList) -> BoundedNodeList:
    result = BoundedNodeList(nodes)
    for node in result:
        if isinstance(node, IfNode):
            node.conditions_nodelists = [
                (condition, bound_nodes(children))
                for condition, children in node.conditions_nodelists
            ]
        elif isinstance(node, BoundedForNode):
            node.nodelist_loop = bound_nodes(node.nodelist_loop)
            node.nodelist_empty = bound_nodes(node.nodelist_empty)
    return result


def check_value(value: object) -> None:
    if isinstance(value, str):
        check_text(value)
    elif isinstance(value, list | tuple | dict):
        size = 0
        for part in DjangoJSONEncoder(ensure_ascii=False).iterencode(value):
            size += check_text(part)
            if size > OUTPUT_LIMIT:
                msg = gettext("Template intermediate value exceeds its size limit.")
                raise TemplateSyntaxError(msg)


def check_replace(value: str, old: str, new: str) -> None:
    size = check_text(value)
    old_size = check_text(old)
    new_size = check_text(new)
    count = value.count(old) if old else len(value) + 1
    if size + count * (new_size - old_size) > OUTPUT_LIMIT:
        msg = gettext("Template replacement exceeds its size limit.")
        raise TemplateSyntaxError(msg)


def bounded_filter(name: str, function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def render(value: Any, *args: Any, **kwargs: Any) -> Any:  # ruff: ignore[any-type]
        _budget.get().check()
        if name not in {"length", "first", "last", "slice", "random"}:
            check_value(value)
        for arg in args:
            check_value(arg)
        if name in {"center", "ljust", "rjust"} and args:
            try:
                width = int(args[0])
            except (ValueError, TypeError):
                pass
            else:
                if width > OUTPUT_LIMIT:
                    msg = gettext("Template padding exceeds its size limit.")
                    raise TemplateSyntaxError(msg)
        if name in {"stringformat", "floatformat"} and args:
            for number in re.findall(r"\d+", str(args[0])):
                if len(number) > 7 or int(number) > OUTPUT_LIMIT:
                    msg = gettext("Template formatting exceeds its size limit.")
                    raise TemplateSyntaxError(msg)
        if name == "join" and args:
            if not hasattr(value, "__len__"):
                value = list(islice(value, OUTPUT_LIMIT + 1))
            size = max(len(value) - 1, 0) * len(str(args[0]).encode("utf-8"))
            for item in value:
                _budget.get().check()
                size += len(str(item).encode("utf-8"))
                if size > OUTPUT_LIMIT:
                    msg = gettext("Template join exceeds its size limit.")
                    raise TemplateSyntaxError(msg)
        result = function(value, *args, **kwargs)
        _budget.get().check()
        check_value(result)
        return result

    return render


# Engine requires a string whose interpolation reports missing variables.
class InvalidString(str):  # ruff: ignore[subclass-builtin]
    __slots__ = ()

    def __mod__(self, other: object) -> Never:
        msg = gettext('Undefined variable: "%s"') % other
        raise TemplateSyntaxError(msg)


class RestrictedEngine(Engine):
    default_builtins: ClassVar[list[str]] = [
        "django.template.defaultfilters",
        "weblate.utils.templatetags.safe_render",
    ]

    def __init__(self) -> None:
        super().__init__(autoescape=False, string_if_invalid=InvalidString("%s"))

    def get_template_builtins(self, builtins: list[str]) -> list[Library]:
        result = []
        for original in super().get_template_builtins(builtins):
            library = Library()
            library.tags = original.tags.copy()
            library.filters = {
                name: bounded_filter(name, function)
                for name, function in original.filters.items()
            }
            result.append(library)
        return result


def render_bounded(source: str, values: dict[str, Any]) -> str:
    check_text(source, SOURCE_LIMIT)
    token = _budget.set(RenderBudget())
    try:
        template = Template(source, engine=RestrictedEngine())
        template.nodelist = bound_nodes(template.nodelist)
        return template.render(Context(values, autoescape=False))
    finally:
        _budget.reset(token)
