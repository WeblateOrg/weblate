# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Explicit, bounded handlers for the supported Django template filters."""

# Exact types exclude subclasses with application-defined hooks.
# pylint: disable=unidiomatic-typecheck

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from functools import partial
from typing import TYPE_CHECKING, Any
from unicodedata import combining, normalize

from django.utils.safestring import SafeString
from django.utils.translation import gettext

from weblate.utils.render_limits import OUTPUT_LIMIT

if TYPE_CHECKING:
    from collections.abc import Callable

    from weblate.utils.render_engine import RenderBudget

TEXT = {str, SafeString}
SCALARS = TEXT | {int, float, bool, type(None), Decimal, date, datetime, time}
INDEXABLE = {list, tuple, str, SafeString}
DICTIONARY_VIEWS = {type({}.keys()), type({}.values()), type({}.items())}  # pylint: disable=unhashable-member
ITERABLES = INDEXABLE | DICTIONARY_VIEWS | {dict}
FORMAT = re.compile(r"[#0 +\-]*(\d*)(?:\.(\d+))?[diouxXeEfFgGcrsa%]\Z")


@dataclass
class FilterCall:
    """A Django filter invocation sharing the current render's budget."""

    budget: RenderBudget
    function: Callable[..., Any]
    value: Any
    args: tuple[Any, ...]
    kwargs: dict[str, Any]

    def scalar_sizes(self) -> tuple[int, int]:
        if type(self.value) not in SCALARS or any(
            type(arg) not in SCALARS for arg in self.args
        ):
            self.budget.reject(
                gettext("This filter requires scalar values and arguments.")
            )
        size = self.budget.scalar_size(self.value)
        argument_size = sum(self.budget.scalar_size(arg) for arg in self.args)
        self.budget.charge(size + argument_size)
        return size, argument_size

    def allocate(self, size: int) -> None:
        if size > OUTPUT_LIMIT:
            self.budget.reject(
                gettext(
                    "Intermediate value would exceed the size limit of %(limit)d bytes."
                )
                % {"limit": OUTPUT_LIMIT}
            )
        self.budget.charge(size)

    def invoke(self) -> Any:  # ruff: ignore[any-type]
        return self.function(self.value, *self.args, **self.kwargs)

    def scalar_result(self) -> object:
        result = self.invoke()
        self.budget.scalar_size(result)
        return result


def number(value: Any, budget: RenderBudget) -> None:  # ruff: ignore[any-type]
    """Bound conversion to an integer before Django attempts it."""
    budget.scalar_size(value)
    if type(value) in TEXT and len(value) > 1240:
        budget.reject(
            gettext("Numeric input exceeds the conversion limit of 1240 characters.")
        )
    if type(value) is Decimal:
        _, digits, exponent = value.as_tuple()
        if not isinstance(exponent, int) or len(digits) + abs(exponent) > 1234:
            budget.reject(gettext("Decimal exceeds the numeric conversion limit."))


def path_filter(call: FilterCall, *, expansion: int = 1) -> object:
    if type(call.value) not in TEXT or any(type(arg) not in TEXT for arg in call.args):
        call.budget.reject(gettext("This filter requires strings."))
    size, argument_size = call.scalar_sizes()
    predicted = max(size * expansion, argument_size)
    call.allocate(predicted)
    call.budget.charge(8 * (size + argument_size + predicted + 1))
    return call.scalar_result()


def string_filter(call: FilterCall, *, expansion: int = 1) -> object:
    if type(call.value) not in TEXT:
        call.budget.scalar_size(call.value)
        call.value = str(call.value)
    return path_filter(call, expansion=expansion)


def value_filter(call: FilterCall) -> object:
    # These filters select an existing value or inspect its truthiness. Trusted
    # containers need neither traversal nor copying, including dictionary views.
    sizes = [
        32 if type(value) in ITERABLES - TEXT else call.budget.scalar_size(value)
        for value in (call.value, *call.args)
    ]
    predicted = max(sizes)
    call.allocate(predicted)
    call.budget.charge(8 * (sum(sizes) + predicted + 1))
    result = call.invoke()
    if type(result) not in ITERABLES - TEXT:
        call.budget.scalar_size(result)
    return result


def yesno_filter(call: FilterCall) -> object:
    if any(type(arg) not in TEXT for arg in call.args):
        call.budget.reject(gettext("Choices must be a string."))
    return value_filter(call)


def length_filter(call: FilterCall) -> object:
    if type(call.value) not in ITERABLES:
        call.budget.reject(
            gettext("Length requires a list, string, dictionary, or dictionary view.")
        )
    call.budget.charge(32)
    return call.invoke()


def indexed_filter(call: FilterCall) -> object:
    if type(call.value) not in INDEXABLE:
        call.budget.reject(gettext("This filter requires a list, tuple, or string."))
    call.budget.charge(32)
    return call.invoke()


def slice_filter(call: FilterCall) -> object:
    if type(call.value) not in INDEXABLE:
        call.budget.reject(gettext("Slicing requires a list, tuple, or string."))
    call.budget.scalar_size(call.args[0])
    text = str(call.args[0])
    if len(text) > 128:
        call.budget.reject(
            gettext("Slice argument exceeds the length limit of 128 characters.")
        )
    if type(call.value) in TEXT:
        call.budget.scalar_size(call.value)
    else:
        try:
            fields = [int(bit) if bit else None for bit in text.split(":")]
            count = len(range(*slice(*fields).indices(len(call.value))))
        except (ValueError, TypeError):
            count = 0  # Django returns the original sequence for invalid slices.
        call.allocate(count * 32)
    call.budget.charge(32 + len(text))
    return call.invoke()


def join_filter(call: FilterCall) -> object:
    if (
        type(call.value) not in ITERABLES
        or type(call.args[0]) not in TEXT
        or call.kwargs.get("autoescape") is not False
    ):
        call.budget.reject(
            gettext(
                "Joining requires an iterable and a string separator with escaping disabled."
            )
        )
    size = max(len(call.value) - 1, 0) * call.budget.scalar_size(call.args[0])
    for item in call.value:
        call.budget.operation()
        if type(item) not in TEXT:
            call.budget.reject(gettext("Joining requires string elements."))
        size += call.budget.scalar_size(item)
        if size > OUTPUT_LIMIT:
            call.budget.reject(
                gettext("Joined value would exceed the size limit of %(limit)d bytes.")
                % {"limit": OUTPUT_LIMIT}
            )
    call.allocate(size)
    return call.invoke()


def sequence_escape_filter(call: FilterCall, *, expansion: int = 1) -> object:
    if type(call.value) not in INDEXABLE:
        call.budget.reject(
            gettext("Sequence escaping requires a list, tuple, or string.")
        )
    call.allocate(len(call.value) * 32)
    size = 0
    for item in call.value:
        if type(item) not in SCALARS:
            call.budget.reject(gettext("Sequence escaping requires scalar elements."))
        size += call.budget.scalar_size(item) * expansion
    call.allocate(size)
    return call.invoke()


def date_filter(call: FilterCall) -> object:
    if type(call.value) not in {date, datetime, time, type(None), str, SafeString}:
        call.budget.reject(
            gettext("Date formatting requires a date, time, string, or None.")
        )
    call.budget.scalar_size(call.value)
    if call.args:
        if type(call.args[0]) not in TEXT | {type(None)}:
            call.budget.reject(gettext("Date format must be a string or None."))
        call.allocate(128 * call.budget.scalar_size(call.args[0]) + 128)
    return call.scalar_result()


def duration_filter(call: FilterCall) -> object:
    if type(call.value) not in {date, datetime, time, type(None), str, SafeString}:
        call.budget.reject(
            gettext("Time comparison requires a date, time, string, or None.")
        )
    call.budget.scalar_size(call.value)
    if call.args and type(call.args[0]) not in {date, datetime, type(None)}:
        call.budget.reject(gettext("Time comparison argument must be a date or None."))
    return call.scalar_result()


def numeric_filter(call: FilterCall) -> object:
    size, argument_size = call.scalar_sizes()
    number(call.value, call.budget)
    for arg in call.args:
        number(arg, call.budget)
    call.allocate(size + argument_size + 2048)
    return call.scalar_result()


def integer_text(value: str) -> bool:
    """Recognize integer text without allocating a potentially large integer."""
    # These four separators are whitespace to str.strip(), but not to int().
    if any(char in value for char in "\x1c\x1d\x1e\x1f"):
        return False
    text = value.strip()
    if text[:1] in {"+", "-"}:
        text = text[1:]
    return (
        bool(text)
        and not text.startswith("_")
        and not text.endswith("_")
        and "__" not in text
        and text.replace("_", "").isdecimal()
    )


def add_filter(call: FilterCall) -> object:
    if type(call.value) in {list, tuple}:
        if type(call.args[0]) is not type(call.value):
            call.budget.reject(
                gettext("Concatenation requires sequences of the same type.")
            )
        call.allocate((len(call.value) + len(call.args[0])) * 32)
        return call.invoke()
    if type(call.value) in TEXT and type(call.args[0]) in TEXT:
        size, argument_size = call.scalar_sizes()
        call.allocate(size + argument_size)
        if max(len(call.value), len(call.args[0])) > 1240:
            call.budget.charge(8 * (size + argument_size))
            if integer_text(call.value) and integer_text(call.args[0]):
                call.budget.reject(
                    gettext(
                        "Numeric input exceeds the conversion limit of 1240 characters."
                    )
                )
            # Either conversion would fail, so Django's result is concatenation.
            # Avoid converting a large numeric operand before reaching that error.
            result = call.value + call.args[0]
            call.budget.scalar_size(result)
            return result
        return call.scalar_result()
    return numeric_filter(call)


def pluralize_filter(call: FilterCall) -> object:
    if call.args and type(call.args[0]) not in TEXT:
        call.budget.reject(gettext("Plural suffixes must be a string."))
    if type(call.value) in {list, tuple, dict}:
        argument_size = sum(call.budget.scalar_size(arg) for arg in call.args)
    else:
        _, argument_size = call.scalar_sizes()
    call.allocate(argument_size + 32)
    return call.scalar_result()


def floatformat_filter(call: FilterCall) -> object:
    size, _ = call.scalar_sizes()
    # Django already bounds coefficient/exponent size at 200 digits.
    if call.args:
        precision = call.args[0]
        if type(precision) in TEXT:
            if len(precision) > 128:
                call.budget.reject(
                    gettext(
                        "Precision argument exceeds the length limit of 128 characters."
                    )
                )
            precision = precision.rstrip("gu") or -1
        else:
            number(precision, call.budget)
        try:
            places = abs(int(precision))
        except (ValueError, TypeError, OverflowError):
            places = 0  # Preserve Django's ordinary invalid-argument behavior.
        if places > 1000:
            call.budget.reject(
                gettext("Formatting precision exceeds the limit of 1000 places.")
            )
    call.allocate(size + 8192)
    return call.scalar_result()


def stringformat_filter(call: FilterCall) -> object:
    size, _ = call.scalar_sizes()
    if type(call.args[0]) not in TEXT or len(call.args[0]) > 128:
        call.budget.reject(
            gettext("Format must be a string of at most 128 characters.")
        )
    match = FORMAT.fullmatch(call.args[0])
    if match is None:
        call.budget.reject(
            gettext(
                "Format must contain one supported conversion without mapping keys or dynamic widths."
            )
        )
    width, precision = (int(part or 0) for part in match.groups())
    if precision > 1000:
        call.budget.reject(
            gettext("Formatting precision exceeds the limit of 1000 places.")
        )
    conversion = call.args[0][-1]
    if conversion not in "sra":
        number(call.value, call.budget)
    expansion = 4 if conversion in "ra" else 1
    call.allocate(size * expansion + width * 4 + precision * 4 + 2048)
    return call.scalar_result()


def padding_filter(call: FilterCall) -> object:
    size, _ = call.scalar_sizes()
    number(call.args[0], call.budget)
    try:
        width = max(int(call.args[0]), 0)
    except (ValueError, TypeError):
        width = 0
    call.allocate(size + max(width - len(str(call.value)), 0))
    return call.scalar_result()


def check_normalization(
    budget: RenderBudget, text: str, *, compatibility: bool
) -> None:
    # Decompose one bounded code point at a time before normalizing the whole
    # string. Reordering is quadratic in combining-run length; letters reset it.
    run = 0
    for char in text:
        budget.charge(32)
        for decomposed in normalize("NFKD" if compatibility else "NFD", char):
            run = run + 1 if combining(decomposed) else 0
            budget.charge(run + 1)


def simple_text_filter(call: FilterCall) -> object:
    size, _ = call.scalar_sizes()
    call.allocate(size + 32)
    return call.scalar_result()


def make_list_filter(call: FilterCall) -> object:
    call.scalar_sizes()
    call.allocate(len(str(call.value)) * 32)
    return call.invoke()


def linenumbers_filter(call: FilterCall) -> object:
    size, _ = call.scalar_sizes()
    count = str(call.value).count("\n") + 1
    call.allocate(size + count * (len(str(count)) + 2))
    return call.scalar_result()


def slugify_filter(call: FilterCall) -> object:
    size, _ = call.scalar_sizes()
    text = str(call.value)
    if not text.isascii():
        check_normalization(call.budget, text, compatibility=True)
    call.allocate(size * 18 + 32)  # Bounded NFKD decomposition expansion.
    return call.scalar_result()


def linebreaks_filter(call: FilterCall) -> object:
    size, _ = call.scalar_sizes()
    call.allocate(size * 8 + 16)
    return call.scalar_result()


def truncate_filter(call: FilterCall, *, normalize_text: bool = False) -> object:
    size, _ = call.scalar_sizes()
    text = str(call.value)
    if normalize_text and not text.isascii():
        check_normalization(call.budget, text, compatibility=False)
    number(call.args[0], call.budget)
    call.allocate(size * 4 + 32)
    return call.scalar_result()


def wordwrap_filter(call: FilterCall) -> object:
    size, _ = call.scalar_sizes()
    number(call.args[0], call.budget)
    call.allocate(size * 8 + 32)  # TextWrapper expands tabs to eight spaces.
    return call.scalar_result()


# Every exposed filter selects its handler here. There is no default handler
# for an unclassified filter, and no second allowlist in the parser or engine.
FILTERS: dict[str, Callable[[FilterCall], object]] = {
    "parentdir": path_filter,
    "dirname": path_filter,
    "stripext": path_filter,
    "cut": string_filter,
    "lower": partial(string_filter, expansion=3),
    "upper": partial(string_filter, expansion=3),
    "capfirst": partial(string_filter, expansion=3),
    "title": partial(string_filter, expansion=3),
    "urlencode": partial(string_filter, expansion=3),
    "iriencode": partial(string_filter, expansion=3),
    "escape": partial(string_filter, expansion=6),
    "force_escape": partial(string_filter, expansion=6),
    "escapejs": partial(string_filter, expansion=6),
    "addslashes": partial(string_filter, expansion=2),
    "default": value_filter,
    "default_if_none": value_filter,
    "yesno": yesno_filter,
    "length": length_filter,
    "first": indexed_filter,
    "last": indexed_filter,
    "random": indexed_filter,
    "slice": slice_filter,
    "join": join_filter,
    "safeseq": sequence_escape_filter,
    "escapeseq": partial(sequence_escape_filter, expansion=6),
    "date": date_filter,
    "time": date_filter,
    "timesince": duration_filter,
    "timeuntil": duration_filter,
    "get_digit": numeric_filter,
    "divisibleby": numeric_filter,
    "filesizeformat": numeric_filter,
    "add": add_filter,
    "pluralize": pluralize_filter,
    "floatformat": floatformat_filter,
    "stringformat": stringformat_filter,
    "center": padding_filter,
    "ljust": padding_filter,
    "rjust": padding_filter,
    "safe": simple_text_filter,
    "phone2numeric": simple_text_filter,
    "wordcount": simple_text_filter,
    "make_list": make_list_filter,
    "linenumbers": linenumbers_filter,
    "slugify": slugify_filter,
    "linebreaks": linebreaks_filter,
    "linebreaksbr": linebreaks_filter,
    "truncatechars": partial(truncate_filter, normalize_text=True),
    "truncatewords": truncate_filter,
    "wordwrap": wordwrap_filter,
    "json": FilterCall.invoke,
    "python": FilterCall.invoke,
}
