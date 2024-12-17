# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import threading

from pyparsing import Optional, ParserElement, QuotedString, Regex, ZeroOrMore


def single_value_flag(func, validation=None):
    def parse_values(val):
        if not val:
            msg = "Missing required parameter"
            raise ValueError(msg)
        if len(val) > 1:
            msg = "Too many parameters"
            raise ValueError(msg)
        result = func(val[0])
        if validation is not None:
            validation(result)
        return result

    return parse_values


def length_validation(length: int):
    def validate_length(val) -> None:
        if len(val) > length:
            msg = "String too long"
            raise ValueError(msg)

    return validate_length


def multi_value_flag(
    func, minimum: int = 1, maximum: int | None = None, modulo: int | None = None
):
    def parse_values(val):
        if modulo and len(val) % modulo != 0:
            msg = "Number of parameter is not even"
            raise ValueError(msg)
        if minimum and len(val) < minimum:
            msg = "Missing required parameter"
            raise ValueError(msg)
        if maximum and len(val) > maximum:
            msg = "Too many parameters"
            raise ValueError(msg)
        return [func(x) for x in val]

    return parse_values


class RawQuotedString(QuotedString):
    def __init__(self, quote_char: str, esc_char: str = "\\") -> None:
        super().__init__(quote_char, esc_char=esc_char, convert_whitespace_escapes=True)
        # unlike the QuotedString this replaces only escaped quotes and not all chars
        self.unquote_scan_re = re.compile(
            rf"({'|'.join(re.escape(k) for k in self.ws_map)})|({re.escape(self.esc_char)}[{re.escape(quote_char)}{re.escape(esc_char)}])|(\n|.)",
            flags=self.re_flags,
        )


SYNTAXCHARS = {",", ":", '"', "'", "\\"}


def get_flags_parser() -> ParserElement:
    flag_name = Regex(r"""[^,:"' \r\n\t]([^,:"']*[^,:"' \r\n\t])?""")

    regex_string = "r" + RawQuotedString('"')

    flag_param = Optional(
        regex_string | flag_name | RawQuotedString("'") | RawQuotedString('"')
    )

    flag = flag_name + ZeroOrMore(":" + flag_param)

    return Optional(flag) + ZeroOrMore("," + Optional(flag))


FLAGS_PARSER: ParserElement = get_flags_parser()
FLAGS_PARSER_LOCK = threading.Lock()
