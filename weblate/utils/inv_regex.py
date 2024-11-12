# Copyright © 2008, Paul McGuire
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: MIT
#
# Based on https://github.com/pyparsing/pyparsing/blob/master/examples/inv_regex.py

import string

from pyparsing import (
    Combine,
    Empty,
    Literal,
    OpAssoc,
    ParseException,
    ParseFatalException,
    ParserElement,
    ParseResults,
    Regex,
    SkipTo,
    Suppress,
    Word,
    infix_notation,
    nums,
    one_of,
    printables,
    srange,
)


class CharacterRangeEmitter:
    def __init__(self, chars) -> None:
        # remove duplicate chars in character range, but preserve original order,
        # this is based on dict being ordered
        self.charset = "".join(dict.fromkeys(chars).keys())

    def __str__(self) -> str:
        return "[" + self.charset + "]"

    def __repr__(self) -> str:
        return "[" + self.charset + "]"

    def make_generator(self):
        def gen_chars():
            yield self.charset[0]

        return gen_chars


class OptionalEmitter:
    def __init__(self, expr) -> None:
        self.expr = expr

    def make_generator(self):
        def optional_gen():
            yield ""

        return optional_gen


class DotEmitter:
    def make_generator(self):
        def dot_gen():
            yield "."

        return dot_gen


class GroupEmitter:
    def __init__(self, exprs) -> None:
        self.exprs = ParseResults(exprs)

    def make_generator(self):
        def group_gen():
            def recurse_list(elist):
                if len(elist) == 1:
                    yield from elist[0].make_generator()()
                else:
                    for s in elist[0].make_generator()():
                        for s2 in recurse_list(elist[1:]):
                            yield s + s2

            if self.exprs:
                yield from recurse_list(self.exprs)

        return group_gen


class AlternativeEmitter:
    def __init__(self, exprs) -> None:
        self.exprs = exprs

    def make_generator(self):
        def alt_gen():
            for e in self.exprs:
                yield from e.make_generator()()

        return alt_gen


class LiteralEmitter:
    def __init__(self, lit) -> None:
        self.lit = lit

    def __str__(self) -> str:
        return "Lit:" + self.lit

    def __repr__(self) -> str:
        return "Lit:" + self.lit

    def make_generator(self):
        def lit_gen():
            yield self.lit

        return lit_gen


def handle_range(toks):
    return CharacterRangeEmitter(srange(toks[0]))


def handle_repetition(toks):
    toks = toks[0]
    if toks[1] == "+":
        return GroupEmitter([toks[0]])
    if toks[1] in "*?":
        return OptionalEmitter(toks[0])
    if "count" in toks:
        return GroupEmitter([toks[0]] * int(toks.count))
    if "minCount" in toks:
        mincount = int(toks.minCount)
        maxcount = int(toks.maxCount)
        optcount = maxcount - mincount
        if optcount:
            opt = OptionalEmitter(toks[0])
            for _i in range(1, optcount):
                opt = OptionalEmitter(GroupEmitter([toks[0], opt]))
            return GroupEmitter([toks[0]] * mincount + [opt])
        return [toks[0]] * mincount
    msg = ""
    raise ParseFatalException(msg, 0, f"Unsupported repetition {toks!r}")


def handle_literal(toks):
    lit = ""
    for t in toks:
        if t[0] == "\\":
            if t[1] == "t":
                lit += "\t"
            else:
                lit += t[1]
        else:
            lit += t
    return LiteralEmitter(lit)


def handle_macro(toks):
    macro_char = toks[0][1]
    if macro_char == "d":
        return CharacterRangeEmitter(string.digits)
    if macro_char == "w":
        return CharacterRangeEmitter(srange("[A-Za-z0-9_]"))
    if macro_char in {"s", "W"}:
        return LiteralEmitter(" ")
    msg = ""
    raise ParseFatalException(msg, 0, f"unsupported macro character ({macro_char})")


def handle_boundary(toks):
    return LiteralEmitter("")


def handle_sequence(toks):
    return GroupEmitter(toks[0])


def handle_dot():
    return CharacterRangeEmitter(printables)


def handle_alternative(toks):
    return AlternativeEmitter(toks[0])


def get_parser():
    orig_whitespace = ParserElement.DEFAULT_WHITE_CHARS
    ParserElement.set_default_whitespace_chars("")
    (
        lbrack,
        rbrack,
        lbrace,
        rbrace,
        _lparen,
        _rparen,
        _colon,
        _qmark,
        dollar,
        cflex,
    ) = map(Literal, "[]{}():?$^")

    re_macro = Combine("\\" + one_of(list("dwsW")))
    escaped_char = ~re_macro + Combine("\\" + one_of(list(printables)))
    re_literal_char = (
        "".join(c for c in printables if c not in r"\[]{}().*?+|$^") + " \t"
    )

    re_range = Combine(lbrack + SkipTo(rbrack, ignore=escaped_char) + rbrack)
    re_literal = escaped_char | one_of(list(re_literal_char))
    re_non_capture_group = Suppress(Regex(r"\?[aiLmsux:-]"))
    re_dot = Literal(".")
    re_boundary = cflex | dollar
    repetition = (
        (lbrace + Word(nums)("count") + rbrace)
        | (lbrace + Word(nums)("minCount") + "," + Word(nums)("maxCount") + rbrace)
        | one_of(list("*+?"))
    )

    re_range.setParseAction(handle_range)
    re_literal.setParseAction(handle_literal)
    re_macro.setParseAction(handle_macro)
    re_dot.setParseAction(handle_dot)
    re_boundary.setParseAction(handle_boundary)

    re_term = (
        re_boundary | re_literal | re_range | re_macro | re_dot | re_non_capture_group
    )
    re_expr = infix_notation(
        re_term,
        [
            (repetition, 1, OpAssoc.LEFT, handle_repetition),
            (Empty(), 2, OpAssoc.LEFT, handle_sequence),
            (Suppress("|"), 2, OpAssoc.LEFT, handle_alternative),
        ],
    )
    ParserElement.set_default_whitespace_chars(orig_whitespace)
    return re_expr


RE_PARSER = get_parser()


def invert_re(regex):
    """
    Return a list of examples of minimal strings that match the expression.

    This is a single purpose generator to optimize database queries in Weblate.
    """
    from weblate.utils.errors import report_error

    try:
        invre = GroupEmitter(RE_PARSER.parse_string(regex)).make_generator()
    except ParseException:
        report_error("Regexp parser")
        return []
    return invre()
