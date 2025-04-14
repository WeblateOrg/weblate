# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: S105

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING, Any, ClassVar, cast

from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy
from lxml import etree

from weblate.checks.models import CHECKS
from weblate.checks.parser import (
    FLAGS_PARSER,
    FLAGS_PARSER_LOCK,
    SYNTAXCHARS,
    length_validation,
    multi_value_flag,
    single_value_flag,
)
from weblate.fonts.utils import get_font_weight
from weblate.trans.autofixes import AUTOFIXES
from weblate.trans.defines import VARIANT_KEY_LENGTH

if TYPE_CHECKING:
    from collections.abc import Iterator


def discard_flag_validation(name: str) -> None:
    """Raise ValueError when parameter is not a valid flag name."""
    if (
        name not in TYPED_FLAGS
        and name not in PLAIN_FLAGS
        and name not in IGNORE_CHECK_FLAGS
    ):
        msg = f"Does not match flag name: {name}"
        raise ValueError(msg)


PLAIN_FLAGS = {
    v.enable_string: v.name
    for k, v in CHECKS.items()
    if v.default_disabled and not v.param_type
}
TYPED_FLAGS = {v.enable_string: v.name for k, v in CHECKS.items() if v.param_type}
TYPED_FLAGS_ARGS = {
    v.enable_string: v.param_type for k, v in CHECKS.items() if v.param_type
}

PLAIN_FLAGS["rst-text"] = gettext_lazy("RST text")
PLAIN_FLAGS["md-text"] = gettext_lazy("Markdown text")
PLAIN_FLAGS["xml-text"] = gettext_lazy("XML text")
PLAIN_FLAGS["dos-eol"] = gettext_lazy("DOS line endings")
PLAIN_FLAGS["url"] = gettext_lazy("URL")
PLAIN_FLAGS["auto-java-messageformat"] = gettext_lazy(
    "Automatically detect Java MessageFormat"
)
PLAIN_FLAGS["read-only"] = gettext_lazy("Read-only")
PLAIN_FLAGS["strict-same"] = gettext_lazy("Strict unchanged check")
PLAIN_FLAGS["strict-format"] = gettext_lazy("Strict format string checks")
PLAIN_FLAGS["forbidden"] = gettext_lazy("Forbidden translation")
PLAIN_FLAGS["terminology"] = gettext_lazy("Terminology")
PLAIN_FLAGS["ignore-all-checks"] = gettext_lazy("Ignore all checks")
PLAIN_FLAGS["case-insensitive"] = gettext_lazy("Use case insensitive placeholders")

DISCARD_FLAG = "discard"

TYPED_FLAGS["font-family"] = gettext_lazy("Font family")
TYPED_FLAGS_ARGS["font-family"] = single_value_flag(str)
TYPED_FLAGS["font-size"] = gettext_lazy("Font size")
TYPED_FLAGS_ARGS["font-size"] = single_value_flag(int)
TYPED_FLAGS["font-weight"] = gettext_lazy("Font weight")
TYPED_FLAGS_ARGS["font-weight"] = single_value_flag(get_font_weight)
TYPED_FLAGS["font-spacing"] = gettext_lazy("Font spacing")
TYPED_FLAGS_ARGS["font-spacing"] = single_value_flag(int)
TYPED_FLAGS["icu-flags"] = gettext_lazy("ICU MessageFormat flags")
TYPED_FLAGS_ARGS["icu-flags"] = multi_value_flag(str)
TYPED_FLAGS["icu-tag-prefix"] = gettext_lazy("ICU MessageFormat tag prefix")
TYPED_FLAGS_ARGS["icu-tag-prefix"] = single_value_flag(str)
TYPED_FLAGS["priority"] = gettext_lazy("Priority")
TYPED_FLAGS_ARGS["priority"] = single_value_flag(int)
TYPED_FLAGS["max-length"] = gettext_lazy("Maximum length of translation")
TYPED_FLAGS_ARGS["max-length"] = single_value_flag(int)
TYPED_FLAGS["replacements"] = gettext_lazy("Replacements while rendering")
TYPED_FLAGS_ARGS["replacements"] = multi_value_flag(str, modulo=2)
TYPED_FLAGS["variant"] = gettext_lazy("String variant")
TYPED_FLAGS_ARGS["variant"] = single_value_flag(
    str, length_validation(VARIANT_KEY_LENGTH)
)
TYPED_FLAGS["fluent-type"] = gettext_lazy("Fluent type")
TYPED_FLAGS_ARGS["fluent-type"] = single_value_flag(str)
TYPED_FLAGS[DISCARD_FLAG] = gettext_lazy("Discard flag")
TYPED_FLAGS_ARGS[DISCARD_FLAG] = single_value_flag(str, discard_flag_validation)


IGNORE_CHECK_FLAGS = {check.ignore_string for check in CHECKS.values()} | set(
    AUTOFIXES.get_ignore_strings()
)

FLAG_ALIASES = {"markdown-text": "md-text"}


def _parse_flags_text(flags: str) -> Iterator[str | tuple[Any, ...]]:
    """Parse comma separated list of flags."""
    state = 0
    name: str
    value: list[Any] = []

    with FLAGS_PARSER_LOCK:
        tokens = list(FLAGS_PARSER.parse_string(flags, parse_all=True))

    for pos, token in enumerate(tokens):
        if state == 0 and token == ",":
            pass
        elif state == 0:
            # Handle aliases
            name = FLAG_ALIASES.get(token, token)
            value = [name]
            state = 1
        elif state == 1 and token == ",":
            # End of flag
            state = 0
            yield name
        elif state in {1, 3} and token == ":":
            # Value separator
            state = 2
        elif state == 2 and token == ",":
            # Flag with empty parameter
            state = 0
            value.append("")
            yield tuple(value)
        elif state == 2 and token == ":":
            # Empty param
            value.append("")
        elif state == 2:
            if (
                token == "r"
                and pos + 1 < len(tokens)
                and tokens[pos + 1] not in {",", ":"}
            ):
                # Regex prefix, value follows
                state = 4
            else:
                # Value
                value.append(token)
                state = 3
        elif state == 4:
            # Regex value
            value.append(re.compile(token))
            state = 3
        elif state == 3 and token == ",":
            # Last value
            yield tuple(value)
            state = 0
        else:
            msg = f"Unexpected token: {token}, state={state}"
            raise ValueError(msg)

    # With state 0 there was nothing parsed yet
    if state > 0:
        if state == 2:
            # There was empty value
            value.append("")
        # Is this flag or flag with value
        if len(value) > 1:
            yield tuple(value)
        else:
            yield name


@lru_cache(maxsize=512)
def parse_flags_text(flags: str) -> tuple[str | tuple[Any, ...], ...]:
    """Parse comma separated list of flags."""
    return tuple(_parse_flags_text(flags))


def parse_flags_xml(flags: etree._Element) -> Iterator[str | tuple[Any, ...]]:
    """Parse comma separated list of flags."""
    maxwidth = flags.get("maxwidth")
    sizeunit = flags.get("size-unit")
    if maxwidth:
        if sizeunit in {None, "pixel", "point"}:
            yield "max-size", maxwidth
        elif sizeunit in {"byte", "char"}:
            yield "max-length", maxwidth
    font = flags.get("font")
    if font:
        font_parts = font.split(";")
        yield "font-family", font_parts[0].strip().replace(" ", "_")
        if len(font_parts) > 1:
            yield "font-size", font_parts[1].strip()
        if len(font_parts) > 2:
            yield "font-weight", font_parts[2].strip()
    text = flags.get("weblate-flags")
    if text:
        yield from parse_flags_text(text)


class Flags:
    _apply_discard: ClassVar[bool] = True

    def __init__(self, *args) -> None:
        self._items: dict[str, str | tuple[Any, ...]] = {}
        for flags in args:
            self.merge(flags)

    def get_items(
        self, flags: str | etree._Element | Flags | tuple[str | tuple[Any, ...]] | None
    ) -> tuple[str | tuple[Any, ...], ...]:
        if flags is None:
            return ()
        if isinstance(flags, str):
            return parse_flags_text(flags)
        if isinstance(flags, etree._Element):  # noqa: SLF001
            return tuple(parse_flags_xml(flags))
        if isinstance(flags, Flags):
            return flags.items()
        return flags

    def merge(
        self, flags: str | etree._Element | Flags | tuple[str | tuple[Any, ...]] | None
    ) -> None:
        for flag in self.get_items(flags):
            if (
                self._apply_discard
                and isinstance(flag, tuple)
                and len(flag) == 2
                and flag[0] == DISCARD_FLAG
            ):
                # Discard the current value if present
                self._items.pop(flag[1], None)
            elif isinstance(flag, tuple):
                self._items[flag[0]] = flag
            elif flag and flag not in {"fuzzy", "#"}:
                # Ignore some flags
                self._items[flag] = flag

    def remove(
        self, flags: str | etree._Element | Flags | tuple[str | tuple[Any, ...]] | None
    ) -> None:
        for flag in self.get_items(flags):
            if isinstance(flag, tuple):
                key = flag[0]
                current = self._items.get(key)
                if current is None:
                    continue
                if isinstance(current, str):
                    continue
                if flag == current:
                    del self._items[key]
            else:
                self._items.pop(flag, None)

    def has_value(self, key: str):
        return isinstance(self._items.get(key), tuple)

    def get_value_raw(self, key: str) -> tuple[Any, ...]:
        return cast("tuple", self._items[key])[1:]

    def get_value(self, key: str):
        return TYPED_FLAGS_ARGS[key](self.get_value_raw(key))

    def get_value_fallback(self, key: str, fallback):
        try:
            value = self.get_value_raw(key)
        except KeyError:
            return fallback
        try:
            return TYPED_FLAGS_ARGS[key](value)
        except KeyError:
            return fallback

    def items(self):
        return set(self._items.values())

    def __iter__(self):
        return self._items.__iter__()

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def __bool__(self) -> bool:
        return bool(self._items)

    @staticmethod
    def format_value(value):
        # Regexp objects
        prefix = ""
        if hasattr(value, "pattern"):
            value = value.pattern
            prefix = "r"
        if prefix or " " in value or any(c in value for c in SYNTAXCHARS):
            return '{}"{}"'.format(
                prefix,
                value.replace('"', r"\"").replace("\n", "\\n").replace("\r", "\\r"),
            )
        return value

    @classmethod
    def format_flag(cls, flag):
        if isinstance(flag, tuple):
            return ":".join(cls.format_value(val) for val in flag)
        return cls.format_value(flag)

    def _format_values(self):
        return (self.format_flag(item) for item in self._items.values())

    def format(self) -> str:
        return ", ".join(sorted(self._format_values()))

    def validate(self) -> None:
        for item in self._items.values():
            if isinstance(item, tuple):
                name, value = item[0], item[1:]
            else:
                name = item
                value = None

            is_typed = name in TYPED_FLAGS
            is_plain = name in PLAIN_FLAGS or name in IGNORE_CHECK_FLAGS
            if not is_typed and not is_plain:
                raise ValidationError(gettext('Invalid translation flag: "%s"') % name)
            if value is not None:
                if is_plain:
                    raise ValidationError(
                        gettext('The translation flag has no parameters: "%s"') % name
                    )
                try:
                    self.get_value(name)
                except Exception as error:
                    raise ValidationError(
                        gettext('Wrong parameters for translation flag: "%s"') % name
                    ) from error
            elif is_typed:
                raise ValidationError(
                    gettext('Missing parameters for translation flag: "%s"') % name
                )

    def set_value(self, name: str, value: str) -> None:
        self._items[name] = (name, value)

    def has_any(self, flags: set[str]) -> bool:
        return bool(flags & set(self._items.keys()))


class FlagsValidator(Flags):
    _apply_discard: ClassVar[bool] = False
