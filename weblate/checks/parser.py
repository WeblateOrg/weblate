#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import re

from pyparsing import Optional, QuotedString, Regex, ZeroOrMore


def single_value_flag(func):
    def parse_values(val):
        if not val:
            raise ValueError("Missing required parameter")
        if len(val) > 1:
            raise ValueError("Too many parameters")
        return func(val[0])

    return parse_values


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
    def __init__(self, quote_char, esc_char="\\"):
        super().__init__(quote_char, esc_char=esc_char, convert_whitespace_escapes=True)
        # unlike the QuotedString this replaces only escaped quotes and not all chars
        self.escCharReplacePattern = (
            re.escape(esc_char)
            + "(["
            + re.escape(quote_char)
            + re.escape(esc_char)
            + "])"
        )


SYNTAXCHARS = {",", ":", '"', "'", "\\"}

FlagName = Regex(r"""[^,:"'\\ \r\n\t]([^,:"'\\]*[^,:"'\\ \r\n\t])?""")

RegexString = "r" + RawQuotedString('"')

FlagParam = Optional(
    RegexString | FlagName | RawQuotedString("'") | RawQuotedString('"')
)

Flag = FlagName + ZeroOrMore(":" + FlagParam)

FlagsParser = Optional(Flag) + ZeroOrMore("," + Optional(Flag))
