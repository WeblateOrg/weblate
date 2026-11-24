# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Restricted template engine with bounded intermediate values and loop work."""

# Exact types exclude subclasses with application-defined hooks.
# pylint: disable=unidiomatic-typecheck

from __future__ import annotations

import math
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time
from decimal import Decimal
from functools import cache, wraps
from time import monotonic
from typing import TYPE_CHECKING, Any, ClassVar, Never, cast

from django.template import Context, Engine, Library, Template, TemplateSyntaxError
from django.template.base import (
    FilterExpression,
    Lexer,
    NodeList,
    Parser,
    TextNode,
    Token,
    TokenType,
    Variable,
    VariableDoesNotExist,
    VariableNode,
    render_value_in_context,
)
from django.template.defaulttags import ForNode, IfNode
from django.template.library import SimpleNode
from django.template.smartif import OPERATORS
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext

from weblate.utils import render_policy
from weblate.utils.render_filters import (
    FILTERS,
    INDEXABLE,
    ITERABLES,
    SCALARS,
    FilterCall,
)
from weblate.utils.render_limits import (
    LOOP_LIMIT,
    OUTPUT_LIMIT,
    RENDER_TIMEOUT,
    SOURCE_LIMIT,
)
from weblate.utils.render_policy import TemplateDiagnosticError
from weblate.utils.render_serialization import serialize

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from weblate.utils.render_context import TemplateContext


def check_text(value: str, limit: int = OUTPUT_LIMIT) -> int:
    if len(value) > limit:
        msg = gettext("Template value exceeds its size limit.")
        raise TemplateDiagnosticError(msg)
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        msg = gettext("Template text is not valid UTF-8.")
        raise TemplateDiagnosticError(msg) from error
    if size > limit:
        msg = gettext("Template value exceeds its size limit.")
        raise TemplateDiagnosticError(msg)
    return size


class RenderBudget:
    def __init__(self, *, for_validation: bool = False) -> None:
        self.for_validation = for_validation
        self.compiling = False
        self.iterations = 0
        self.operations = 0
        self.filters = 0
        self.work = 0
        self.failure: Exception | None = None
        self.deadline = monotonic() + RENDER_TIMEOUT
        self.location: tuple[int | None, str | None] = (None, None)

    def annotate(self, error: Exception) -> None:
        # Keep the innermost location, including when smart-if catches an abort.
        error.__dict__.setdefault("render_location", self.location)

    @contextmanager
    def scope(
        self, token: Token | None = None, operation: str | None = None
    ) -> Generator[None, None, None]:
        previous = self.location
        line, current_operation = previous
        if token is not None:
            line = token.lineno
            current_operation = self.tag_operation(token)
        self.location = (line, operation or current_operation)
        try:
            yield
        except Exception as error:
            self.annotate(error)
            raise
        finally:
            self.location = previous

    def fail(self, error: Exception) -> Never:
        # Django's smart-if operators catch Exception. Never lose an abort.
        self.annotate(error)
        self.failure = self.failure or error
        raise self.failure

    def reject(self, message: str) -> Never:
        self.fail(TemplateDiagnosticError(message))

    @staticmethod
    def tag_operation(token: Token) -> str | None:
        if token.token_type != TokenType.BLOCK:
            return None
        parts = token.contents.split(maxsplit=1)
        if parts and parts[0] in render_policy.TEMPLATE_TAGS:
            return gettext('Tag "%(name)s"') % {"name": parts[0]}
        return None

    def format_error(self, error: Exception, *, multiline: bool) -> str:
        line, operation = getattr(error, "render_location", (None, None))
        token = getattr(error, "token", None)
        if token is not None:
            line = token.lineno
            operation = operation or self.tag_operation(token)
        # Native exception messages can include context values. Keep their
        # control-flow semantics, but expose only a safe reason if they escape.
        if isinstance(error, TemplateDiagnosticError):
            message = str(error)
        elif isinstance(error, TemplateSyntaxError):
            # Django's compiler can quote the submitted template. Native
            # evaluation errors can instead quote repository context.
            message = (
                str(error)
                if self.for_validation and self.compiling
                else gettext("Invalid template syntax.")
            )
        elif isinstance(error, VariableDoesNotExist):
            message = gettext("Undefined template variable.")
        elif isinstance(error, UnicodeError):
            message = gettext("Text is not valid UTF-8.")
        elif isinstance(error, ZeroDivisionError):
            message = gettext("Division by zero is not supported.")
        elif isinstance(error, OverflowError):
            message = gettext("Numeric value is too large for this operation.")
        elif isinstance(error, ArithmeticError):
            message = gettext("Numeric operation failed.")
        elif isinstance(error, TypeError):
            message = gettext("Value or argument has an unsupported type.")
        elif isinstance(error, IndexError):
            message = gettext("Value or argument is incomplete or out of range.")
        else:
            message = gettext("Value or argument has an invalid format.")
        if operation is not None:
            message = gettext("%(operation)s: %(message)s") % {
                "operation": operation,
                "message": message,
            }
        if multiline and line is not None:
            message = gettext("Line %(line)d: %(message)s") % {
                "line": line,
                "message": message,
            }
        return message

    def check(self) -> None:
        if self.failure is not None:
            raise self.failure
        if monotonic() >= self.deadline:
            msg = gettext("Template rendering exceeded its time limit.")
            self.fail(TemplateDiagnosticError(msg))

    def operation(self) -> None:
        self.check()
        self.operations += 1
        if self.operations > render_policy.OPERATION_LIMIT:
            self.reject(
                gettext("Template exceeds the operation limit of %(limit)d.")
                % {"limit": render_policy.OPERATION_LIMIT}
            )

    def charge(self, size: int) -> None:
        self.check()
        self.work += size
        if self.work > render_policy.WORK_LIMIT:
            self.reject(
                gettext(
                    "Template exceeds the cumulative work limit of %(limit)d bytes."
                )
                % {"limit": render_policy.WORK_LIMIT}
            )

    def scalar_size(self, value: object) -> int:
        if type(value) is str or type(value) is SafeString:
            if len(value) > OUTPUT_LIMIT:
                self.reject(
                    gettext("Template value exceeds the size limit of %(limit)d bytes.")
                    % {"limit": OUTPUT_LIMIT}
                )
            size = len(value.encode("utf-8"))
            if size > OUTPUT_LIMIT:
                self.reject(
                    gettext("Template value exceeds the size limit of %(limit)d bytes.")
                    % {"limit": OUTPUT_LIMIT}
                )
            self.charge(size)
            return size
        if type(value) in {date, datetime, time, Decimal}:
            text = str(value)
            return self.scalar_size(text)
        if type(value) not in SCALARS:
            self.reject(gettext("Template value must be a supported scalar."))
        if type(value) is int and value.bit_length() > 4096:
            self.reject(gettext("Integer exceeds the numeric limit of 4096 bits."))
        if type(value) is float and not math.isfinite(value):
            self.reject(gettext("Nonfinite numbers are not supported."))
        return 2048 if type(value) is int else 128

    def apply_filter(
        self,
        name: str,
        function: Callable[..., Any],
        value: object,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> object:
        with self.scope(operation=gettext('Filter "%(name)s"') % {"name": name}):
            self.operation()
            self.filters += 1
            if self.filters > render_policy.FILTER_LIMIT:
                self.reject(
                    gettext(
                        "Template exceeds the filter application limit of %(limit)d."
                    )
                    % {"limit": render_policy.FILTER_LIMIT}
                )
            return FILTERS[name](FilterCall(self, function, value, args, kwargs))

    def iteration(self) -> None:
        self.operation()
        self.iterations += 1
        if self.iterations > LOOP_LIMIT:
            msg = gettext("Template rendering exceeded its loop limit.")
            self.fail(TemplateDiagnosticError(msg))


_budget: ContextVar[RenderBudget] = ContextVar("template_render_budget")


class PolicyVariable(Variable):
    def resolve(self, context: Any) -> Any:  # ruff: ignore[any-type]
        budget = _budget.get()
        if self.lookups is None:
            return super().resolve(context)
        current = None
        for index, part in enumerate(self.lookups):
            budget.operation()
            if index == 0:
                # Context scopes include built-in literals and loop variables.
                try:
                    current = context[part]
                except KeyError:
                    raise VariableDoesNotExist(part) from None
            elif type(current) is dict and part in current:
                current = current[part]
            else:
                current = self.lookup(current, part)
        return current

    @staticmethod
    def lookup(value: Any, part: str) -> Any:  # ruff: ignore[any-type]
        budget = _budget.get()
        if type(value) is dict:
            if part == "items":
                return dict.items(value)
            if part == "keys":
                return dict.keys(value)
            if part == "values":
                return dict.values(value)
        # Inspect only the trusted built-in type. Never call a descriptor or
        # arbitrary method on the value; the three dictionary views above are
        # the complete read-only method allowlist.
        if hasattr(type(value), part):
            budget.reject(
                gettext("Attribute access and method calls are not supported.")
            )
        if type(value) in INDEXABLE:
            if len(part) > 128:
                budget.reject(
                    gettext("Index exceeds the length limit of 128 characters.")
                )
            try:
                return value[int(part)]
            except (ValueError, IndexError):
                raise VariableDoesNotExist(part) from None
        raise VariableDoesNotExist(part)


class PolicyFilterExpression(FilterExpression):
    def __init__(self, token: str, parser: Parser) -> None:
        self.source_token = cast("PolicyParser", parser).current_token
        super().__init__(token, parser)
        self.var = self.variable(self.var) if self.is_var else self.constant(self.var)
        for _function, args in self.filters:
            for index, (lookup, arg) in enumerate(args):
                args[index] = (
                    lookup,
                    self.variable(arg) if lookup else self.constant(arg),
                )

    def resolve(self, context: Context, ignore_failures: bool = False) -> Any:  # ruff: ignore[any-type]
        with _budget.get().scope(self.source_token):
            return super().resolve(context, ignore_failures=ignore_failures)

    @staticmethod
    def constant(value: object) -> object:
        _budget.get().scalar_size(value)
        return value

    @staticmethod
    def variable(value: Variable) -> PolicyVariable:
        budget = _budget.get()
        if value.translate:
            budget.reject(gettext("Translated template literals are not supported."))
        if value.lookups is None:
            budget.scalar_size(value.literal)
        return PolicyVariable(value.var)


class PolicyParser(Parser):
    current_token: Token | None = None

    def next_token(self) -> Token:
        self.current_token = super().next_token()
        return self.current_token

    def find_filter(self, filter_name: str) -> Callable[..., Any]:
        try:
            return super().find_filter(filter_name)
        except TemplateSyntaxError as error:
            if _budget.get().for_validation:
                raise
            raise TemplateDiagnosticError(gettext("Invalid filter.")) from error

    def compile_filter(self, token: str) -> FilterExpression:
        with _budget.get().scope(self.current_token):
            return PolicyFilterExpression(token, self)


class RestrictedTemplate(Template):
    def compile_nodelist(self) -> NodeList:
        # RestrictedEngine always disables debug. Grammar and tag compilation
        # remain Django's; only expression construction is adapted.
        parser = PolicyParser(
            Lexer(self.source).tokenize(),
            self.engine.template_libraries,
            self.engine.template_builtins,
            self.origin,
        )
        result = parser.parse()
        self.extra_data = parser.extra_data
        return result


class ConditionValue:
    def __init__(self, value: object) -> None:
        self.value = value

    def eval(self, context: Context) -> object:
        return self.value


class GuardedCondition:
    def __init__(self, node: Any) -> None:  # ruff: ignore[any-type]
        self.node = node
        literal = node
        while literal.id != "literal":
            literal = literal.first
        self.source_token = literal.value.source_token

    def eval(self, context: Context) -> object:
        budget = _budget.get()
        with budget.scope(self.source_token):
            budget.operation()
            try:
                return self.evaluate(context)
            except Exception:
                # Literals must propagate ordinary errors to their owning operator
                # (or IfNode). Swallowing here changes short-circuit semantics.
                if self.node.id == "literal":
                    raise
                # Recorded aborts survive both this catch and smart-if's operators.
                return False
            finally:
                budget.check()

    def evaluate(self, context: Context) -> object:
        budget = _budget.get()
        if self.node.id in {"literal", "and", "or", "not"}:
            return self.node.eval(context)
        left = self.node.first.eval(context)
        right = self.node.second.eval(context)
        if self.node.id in {"is", "is not"}:
            if not (
                left is None
                or right is None
                or type(left) is bool
                or type(right) is bool
            ):
                budget.reject(
                    gettext("Identity comparisons require None, True, or False.")
                )
        else:
            size = budget.scalar_size(left) + budget.scalar_size(right)
            budget.charge(8 * (size + 1))
        # Use Django's operator, including its treatment of incompatible
        # comparisons, after guarding both operands. No condition grammar
        # or operator implementation is duplicated here.
        operator = OPERATORS[self.node.id]()
        operator.first = ConditionValue(left)
        operator.second = ConditionValue(right)
        return operator.eval(context)


def guard_condition(node: Any) -> Any:  # ruff: ignore[any-type]
    guarded = GuardedCondition(node)
    with _budget.get().scope(guarded.source_token):
        if node.id not in {
            "literal",
            "and",
            "or",
            "not",
            "==",
            "!=",
            "<",
            "<=",
            ">",
            ">=",
            "is",
            "is not",
        }:
            _budget.get().reject(gettext("This condition operator is not supported."))
        if node.first is not None:
            node.first = guard_condition(node.first)
        if node.second is not None:
            node.second = guard_condition(node.second)
        return guarded


class OutputBuffer:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.size = 0

    def append(self, value: str) -> None:
        budget = _budget.get()
        budget.check()
        try:
            size = check_text(value)
        except TemplateSyntaxError as error:
            budget.fail(error)
        budget.charge(size)
        self.size += size
        if self.size > OUTPUT_LIMIT:
            msg = gettext("Template output exceeds its size limit.")
            budget.fail(TemplateDiagnosticError(msg))
        self.parts.append(value)

    def render(self) -> SafeString:
        _budget.get().check()
        # Django's NodeList contract; render_template removes this internal marker.
        return mark_safe("".join(self.parts))  # ruff: ignore[suspicious-mark-safe-usage]


class BoundedNodeList(NodeList):
    def render(self, context: Context) -> SafeString:
        output = OutputBuffer()
        for node in self:
            budget = _budget.get()
            with budget.scope(node.token):
                budget.operation()
                try:
                    rendered = cast("str", node.render_annotated(context))
                except TemplateSyntaxError as error:
                    budget.fail(error)
                budget.check()
                output.append(rendered)
        return output.render()


class BoundedVariableNode(VariableNode):
    def render(self, context: Context) -> str:
        budget = _budget.get()
        value = self.filter_expression.resolve(context)
        budget.scalar_size(value)
        return render_value_in_context(value, context)


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
            if type(values) not in ITERABLES:
                budget.reject(
                    gettext(
                        "Loops require a list, string, dictionary, or dictionary view."
                    )
                )
            count = len(values)
            if count > LOOP_LIMIT - budget.iterations:
                msg = gettext("Template rendering exceeded its loop limit.")
                budget.fail(TemplateDiagnosticError(msg))
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
                    if type(item) not in {
                        list,
                        dict,
                        str,
                        SafeString,
                        tuple,
                    }:
                        budget.reject(
                            gettext(
                                "Loop unpacking requires a list, tuple, string, or dictionary."
                            )
                        )
                    size = len(item)
                    if size != len(self.loopvars):
                        msg = gettext(
                            "Loop value cannot be unpacked into its variables."
                        )
                        budget.fail(TemplateDiagnosticError(msg))
                    with context.push(dict(zip(self.loopvars, item, strict=True))):
                        output.append(self.nodelist_loop.render(context))
                else:
                    context[self.loopvars[0]] = item
                    output.append(self.nodelist_loop.render(context))
            return output.render()


def bound_nodes(nodes: NodeList) -> BoundedNodeList:
    result = BoundedNodeList(nodes)
    budget = _budget.get()
    for index, node in enumerate(result):
        with budget.scope(node.token):
            if isinstance(node, IfNode):
                node.conditions_nodelists = [
                    (
                        guard_condition(condition)
                        if condition is not None
                        else condition,
                        bound_nodes(children),
                    )
                    for condition, children in node.conditions_nodelists
                ]
            elif isinstance(node, BoundedForNode):
                node.nodelist_loop = bound_nodes(node.nodelist_loop)
                node.nodelist_empty = bound_nodes(node.nodelist_empty)
            elif isinstance(node, VariableNode):
                replacement = BoundedVariableNode(node.filter_expression)
                replacement.origin = node.origin
                replacement.token = node.token
                result[index] = replacement
            elif type(node) is SimpleNode:
                # The tag module imports this engine, so resolve its function only
                # after Django has loaded the fixed built-in library.
                from weblate.utils.templatetags.safe_render import (  # ruff: ignore[import-outside-top-level]
                    replace,
                )

                if node.func is not replace:
                    budget.reject(gettext("This template tag is not supported."))
            elif not isinstance(node, TextNode):
                budget.reject(gettext("This template node is not supported."))
    return result


def check_replace(value: str, old: str, new: str) -> None:
    budget = _budget.get()
    budget.operation()
    if any(type(item) not in {str, SafeString} for item in (value, old, new)):
        budget.reject(gettext("Replacement requires string values and arguments."))
    size, old_size, new_size = (budget.scalar_size(item) for item in (value, old, new))
    budget.charge(8 * (size + old_size + new_size + 1))
    count = value.count(old) if old else len(value) + 1
    predicted = size + count * (new_size - old_size)
    if predicted > OUTPUT_LIMIT:
        budget.reject(
            gettext(
                "Replacement exceeds the intermediate size limit of %(limit)d bytes."
            )
            % {"limit": OUTPUT_LIMIT}
        )
    budget.charge(8 * predicted)


def serialize_literal(value: object, *, python: bool = False) -> str:
    return serialize(value, _budget.get(), python=python)


def bounded_filter(name: str, function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def render(value: Any, *args: Any, **kwargs: Any) -> Any:  # ruff: ignore[any-type]
        return _budget.get().apply_filter(name, function, value, args, kwargs)

    return render


# Engine requires a string whose interpolation reports missing variables.
class InvalidString(str):  # ruff: ignore[subclass-builtin]
    __slots__ = ()

    def __mod__(self, other: object) -> Never:
        budget = _budget.get(None)
        if budget is not None and budget.for_validation:
            msg = gettext('Undefined variable: "%s"') % other
        else:
            msg = gettext("Undefined template variable.")
        raise TemplateDiagnosticError(msg)


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
                if name in FILTERS
            }
            result.append(library)
        return result


@cache
def get_engine() -> RestrictedEngine:
    return RestrictedEngine()


def render_bounded(
    source: str, values: TemplateContext, *, for_validation: bool = False
) -> str:
    check_text(source, SOURCE_LIMIT)
    if not any(delimiter in source for delimiter in ("{{", "{%", "{#")):
        return source
    budget = RenderBudget(for_validation=for_validation)
    token = _budget.set(budget)
    try:
        result = evaluate_template(source, values, budget)
    except (
        TemplateSyntaxError,
        VariableDoesNotExist,
        TypeError,
        ValueError,
        ArithmeticError,
        IndexError,
    ) as error:
        raise TemplateDiagnosticError(
            budget.format_error(error, multiline="\n" in source)
        ) from error
    else:
        return result
    finally:
        _budget.reset(token)
        # Abort tracebacks reference this budget. Release the reverse reference
        # promptly after failed renders instead of retaining a cycle.
        budget.failure = None


def evaluate_template(
    source: str, values: TemplateContext, budget: RenderBudget
) -> str:
    render_policy.preflight(source, for_validation=budget.for_validation)
    budget.check()
    budget.compiling = True
    template = RestrictedTemplate(source, engine=get_engine())
    budget.compiling = False
    budget.check()
    template.nodelist = bound_nodes(template.nodelist)
    # Assignment tags must not modify the caller's snapshot.
    result = template.render(Context(values.copy(), autoescape=False))
    budget.check()
    return result
