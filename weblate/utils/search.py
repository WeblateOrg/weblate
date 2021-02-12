#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
from datetime import datetime
from functools import lru_cache, reduce
from itertools import chain
from typing import Dict

from dateutil.parser import ParserError, parse
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from jellyfish import damerau_levenshtein_distance
from pyparsing import (
    CaselessKeyword,
    Optional,
    Regex,
    Word,
    infixNotation,
    oneOf,
    opAssoc,
)

from weblate.checks.parser import RawQuotedString
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.db import re_escape, using_postgresql
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_FUZZY,
    STATE_NAMES,
    STATE_READONLY,
    STATE_TRANSLATED,
)


class Comparer:
    """String comparer abstraction.

    The reason is to be able to change implementation.
    """

    def similarity(self, first, second):
        """Returns string similarity in range 0 - 100%."""
        try:
            distance = damerau_levenshtein_distance(first, second)
            return int(
                100 * (1.0 - (float(distance) / max(len(first), len(second), 1)))
            )
        except MemoryError:
            # Too long string, mark them as not much similar
            return 50


# Field type definitions
PLAIN_FIELDS = ("source", "target", "context", "note", "location")
NONTEXT_FIELDS = {
    "priority": "priority",
    "state": "state",
    "pending": "pending",
    "changed": "change__timestamp",
    "change_time": "change__timestamp",
    "added": "timestamp",
    "change_action": "change__action",
}
STRING_FIELD_MAP = {
    "suggestion": "suggestion__target",
    "comment": "comment__comment",
    "key": "context",
    "explanation": "source_unit__explanation",
}
EXACT_FIELD_MAP = {
    "check": "check__check",
    "dismissed_check": "check__check",
    "language": "translation__language__code",
    "component": "translation__component__slug",
    "project": "translation__component__project__slug",
    "changed_by": "change__author__username",
    "suggestion_author": "suggestion__user__username",
    "comment_author": "comment__user__username",
    "label": "source_unit__labels__name",
}
OPERATOR_MAP = {
    ":": "substring",
    ":=": "iexact",
    ":<": "lt",
    ":<=": "lte",
    ":>": "gt",
    ":>=": "gte",
}

# Parsing grammar

AND = CaselessKeyword("AND")
OR = Optional(CaselessKeyword("OR"))
NOT = CaselessKeyword("NOT")

# Search operator
OPERATOR = oneOf(OPERATOR_MAP.keys())

# Field name, explicitely exlude URL like patters
FIELD = Regex(r"""(?!http|ftp|https|mailto)[a-zA-Z_]+""")

# Match token
WORD = Regex(r"""[^ \(\)]([^ '"]*[^ '"\)])?""")
DATE = Word("0123456789:.-T")

# Date range
RANGE = "[" + DATE + "to" + DATE + "]"

# Match value
REGEX_STRING = "r" + RawQuotedString('"')
STRING = REGEX_STRING | RawQuotedString("'") | RawQuotedString('"') | WORD

# Single term, either field specific or not
TERM = (FIELD + OPERATOR + (RANGE | STRING)) | STRING

# Multi term with or without operator
QUERY = Optional(
    infixNotation(
        TERM,
        [
            (
                NOT,
                1,
                opAssoc.RIGHT,
            ),
            (
                AND,
                2,
                opAssoc.LEFT,
            ),
            (
                OR,
                2,
                opAssoc.LEFT,
            ),
        ],
    )
)

# Helper parsing objects


class RegexExpr:
    def __init__(self, tokens):
        self.expr = tokens[1]


REGEX_STRING.addParseAction(RegexExpr)


class RangeExpr:
    def __init__(self, tokens):
        self.start = tokens[1]
        self.end = tokens[3]


RANGE.addParseAction(RangeExpr)


class TermExpr:
    def __init__(self, tokens):
        if len(tokens) == 1:
            self.field = None
            self.operator = ":"
            self.match = tokens[0]
        else:
            self.field, self.operator, self.match = tokens
            self.fixup()

    def __repr__(self):
        return f"<TermExpr: '{self.field}', '{self.operator}', '{self.match}'>"

    def fixup(self):
        # Avoid unwanted lt/gt searches on plain text fields
        if self.field in PLAIN_FIELDS and self.operator not in (":", ":="):
            self.match = self.operator[1:] + self.match
            self.operator = ":"

    def is_field(self, text, context: Dict):
        if text in ("read-only", "readonly"):
            return Q(state=STATE_READONLY)
        if text == "approved":
            return Q(state=STATE_APPROVED)
        if text in ("fuzzy", "needs-editing"):
            return Q(state=STATE_FUZZY)
        if text == "translated":
            return Q(state__gte=STATE_TRANSLATED)
        if text == "untranslated":
            return Q(state__lt=STATE_TRANSLATED)
        if text == "pending":
            return Q(pending=True)

        raise ValueError(f"Unsupported is lookup: {text}")

    def has_field(self, text, context: Dict):  # noqa: C901
        if text == "plural":
            return Q(source__contains=PLURAL_SEPARATOR)
        if text == "suggestion":
            return Q(suggestion__isnull=False)
        if text == "explanation":
            return ~Q(source_unit__explanation="")
        if text == "comment":
            return Q(comment__resolved=False)
        if text in ("resolved-comment", "resolved_comment"):
            return Q(comment__resolved=True)
        if text in ("check", "failing-check", "failing_check"):
            return Q(check__dismissed=False)
        if text in (
            "dismissed-check",
            "dismissed_check",
            "ignored-check",
            "ignored_check",
        ):
            return Q(check__dismissed=True)
        if text == "translation":
            return Q(state__gte=STATE_TRANSLATED)
        if text in ("variant", "shaping"):
            return Q(variant__isnull=False)
        if text == "label":
            return Q(source_unit__labels__isnull=False)
        if text == "context":
            return ~Q(context="")
        if text == "screenshot":
            return Q(screenshots__isnull=False) | Q(
                source_unit__screenshots__isnull=False
            )
        if text == "flags":
            return ~Q(source_unit__extra_flags="")
        if text == "glossary":
            project = context.get("project")
            if not project:
                return Q(source__isnull=True)
            terms = set(
                chain.from_iterable(
                    glossary.glossary_sources for glossary in project.glossaries
                )
            )
            if not terms:
                return Q(source__isnull=True)
            if using_postgresql():
                template = r"[[:<:]]({})[[:>:]]"
            else:
                template = r"(^|[ \t\n\r\f\v])({})($|[ \t\n\r\f\v])"
            return Q(
                source__iregex=template.format(
                    "|".join(re_escape(term) for term in terms)
                )
            )

        raise ValueError(f"Unsupported has lookup: {text}")

    def field_extra(self, field, query, match):
        from weblate.trans.models import Change

        if field in {"changed", "changed_by"}:
            return query & Q(change__action__in=Change.ACTIONS_CONTENT)
        if field == "check":
            return query & Q(check__dismissed=False)
        if field == "dismissed_check":
            return query & Q(check__dismissed=True)

        return query

    def convert_state(self, text):
        if text is None:
            return None
        if text.isdigit():
            return int(text)
        try:
            return STATE_NAMES[text]
        except KeyError:
            raise ValueError(_("Unsupported state: {}").format(text))

    def convert_bool(self, text):
        ltext = text.lower()
        if ltext in ("yes", "true", "on", "1"):
            return True
        if ltext in ("no", "false", "off", "0"):
            return False
        raise ValueError(f"Invalid boolean value: {text}")

    def convert_pending(self, text):
        return self.convert_bool(text)

    def convert_int(self, text):
        return int(text)

    def convert_priority(self, text):
        return self.convert_int(text)

    def convert_datetime(self, text, hour=5, minute=55, second=55, microsecond=0):
        if isinstance(text, RangeExpr):
            return (
                self.convert_datetime(
                    text.start, hour=0, minute=0, second=0, microsecond=0
                ),
                self.convert_datetime(
                    text.end, hour=23, minute=59, second=59, microsecond=999999
                ),
            )
        if text.isdigit() and len(text) == 4:
            year = int(text)
            tzinfo = timezone.get_current_timezone()
            return (
                datetime(
                    year=year,
                    month=1,
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                    tzinfo=tzinfo,
                ),
                datetime(
                    year=year,
                    month=12,
                    day=31,
                    hour=23,
                    minute=59,
                    second=59,
                    microsecond=999999,
                    tzinfo=tzinfo,
                ),
            )
        try:
            # Here we inject 5:55:55 time and if that was not changed
            # during parsing, we assume it was not specified while
            # generating the query
            result = parse(
                text,
                default=timezone.now().replace(
                    hour=hour, minute=minute, second=second, microsecond=microsecond
                ),
            )
        except ParserError as error:
            raise ValueError(_("Invalid timestamp: {}").format(error))
        if result.hour == 5 and result.minute == 55 and result.second == 55:
            return (
                result.replace(hour=0, minute=0, second=0, microsecond=0),
                result.replace(hour=23, minute=59, second=59, microsecond=999999),
            )
        return result

    def convert_change_action(self, text):
        from weblate.trans.models import Change

        try:
            return Change.ACTION_NAMES[text]
        except KeyError:
            return Change.ACTION_STRINGS[text]

    def convert_change_time(self, text):
        return self.convert_datetime(text)

    def convert_changed(self, text):
        return self.convert_datetime(text)

    def convert_added(self, text):
        return self.convert_datetime(text)

    def field_name(self, field, suffix=None):
        if suffix is None:
            suffix = OPERATOR_MAP[self.operator]

        if field in PLAIN_FIELDS:
            return f"{field}__{suffix}"
        if field in STRING_FIELD_MAP:
            return "{}__{}".format(STRING_FIELD_MAP[field], suffix)
        if field in EXACT_FIELD_MAP:
            # Change contains to exact, do not change other (for example regex)
            if suffix == "substring":
                suffix = "iexact"
            return "{}__{}".format(EXACT_FIELD_MAP[field], suffix)
        if field in NONTEXT_FIELDS:
            if suffix not in ("substring", "iexact"):
                return "{}__{}".format(NONTEXT_FIELDS[field], suffix)
            return NONTEXT_FIELDS[field]
        raise ValueError(f"Unsupported field: {field}")

    def as_sql(self, context: Dict):
        field = self.field
        match = self.match
        # Simple term based search
        if not field:
            return (
                Q(source__substring=self.match)
                | Q(target__substring=self.match)
                | Q(context__substring=self.match)
            )

        # Field specific code
        field_method = getattr(self, f"{field}_field", None)
        if field_method is not None:
            return field_method(match, context)

        # Field conversion
        convert_method = getattr(self, f"convert_{field}", None)
        if convert_method is not None:
            match = convert_method(match)

        if isinstance(match, RegexExpr):
            # Regullar expression
            try:
                re.compile(match.expr)
            except re.error as error:
                raise ValueError(_("Invalid regular expression: {}").format(error))
            return Q(**{self.field_name(field, "regex"): match.expr})

        if isinstance(match, tuple):
            start, end = match
            # Ranges
            if self.operator in (":", ":="):
                query = Q(
                    **{
                        self.field_name(field, "gte"): start,
                        self.field_name(field, "lte"): end,
                    }
                )
            elif self.operator in (":>", ":>="):
                query = Q(**{self.field_name(field, "gte"): start})
            else:
                query = Q(**{self.field_name(field, "lte"): end})

        else:
            # Generic query
            query = Q(**{self.field_name(field): match})

        return self.field_extra(field, query, match)


TERM.addParseAction(TermExpr)


def parser_to_query(obj, context: Dict):
    # Simple lookups
    if isinstance(obj, TermExpr):
        return obj.as_sql(context)

    # Operators
    operator = "AND"
    expressions = []
    for item in obj:
        if isinstance(item, str) and item.upper() in ("OR", "AND", "NOT"):
            operator = item.upper()
            continue
        expressions.append(parser_to_query(item, context))

    if not expressions:
        return Q()

    if operator == "NOT":
        return ~expressions[0]
    if operator == "AND":
        return reduce(lambda x, y: x & y, expressions)
    return reduce(lambda x, y: x | y, expressions)


@lru_cache(maxsize=512)
def parse_string(text):
    if "\x00" in text:
        raise ValueError("Invalid query string.")
    return QUERY.parseString(text, parseAll=True)


def parse_query(text, **context):
    parsed = parse_string(text)
    return parser_to_query(parsed, context)
