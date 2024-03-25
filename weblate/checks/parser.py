# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from pyparsing import Optional, QuotedString, Regex, ZeroOrMore


def single_value_flag(func, validation=None):
    def parse_values(val):
        if not val:
            raise ValueError("Missing required parameter")
        if len(val) > 1:
            raise ValueError("Too many parameters")
        result = func(val[0])
        if validation is not None:
            validation(result)
        return result

    return parse_values


def length_validation(length: int):
    def validate_length(val) -> None:
        if len(val) > length:
            raise ValueError("String too long")

    return validate_length


def multi_value_flag(func, minimum=1, maximum=None, modulo=None):
    def parse_values(val):
        if modulo and len(val) % modulo != 0:
            raise ValueError("Number of parameter is not even")
        if minimum and len(val) < minimum:
            raise ValueError("Missing required parameter")
        if maximum and len(val) > maximum:
            raise ValueError("Too many parameters")
        return [func(x) for x in val]

    return parse_values


class RawQuotedString(QuotedString):
    def __init__(self, quote_char, esc_char="\\") -> None:
        super().__init__(quote_char, esc_char=esc_char, convert_whitespace_escapes=True)
        # unlike the QuotedString this replaces only escaped quotes and not all chars
        self.unquote_scan_re = re.compile(
            rf"({'|'.join(re.escape(k) for k in self.ws_map)})|({re.escape(self.esc_char)}[{re.escape(quote_char)}{re.escape(esc_char)}])|(\n|.)",
            flags=self.re_flags,
        )


SYNTAXCHARS = {",", ":", '"', "'", "\\"}

FlagName = Regex(r"""[^,:"' \r\n\t]([^,:"']*[^,:"' \r\n\t])?""")

RegexString = "r" + RawQuotedString('"')

FlagParam = Optional(
    RegexString | FlagName | RawQuotedString("'") | RawQuotedString('"')
)

Flag = FlagName + ZeroOrMore(":" + FlagParam)

FlagsParser = Optional(Flag) + ZeroOrMore("," + Optional(Flag))
