# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from datetime import datetime, timedelta
from functools import lru_cache, reduce
from itertools import chain
from operator import and_, or_
from typing import NoReturn

from dateutil.parser import ParserError, parse
from django.db import transaction
from django.db.models import Q, Value
from django.db.utils import DataError
from django.utils import timezone
from django.utils.translation import gettext
from pyparsing import (
    CaselessKeyword,
    OpAssoc,
    Optional,
    Regex,
    Word,
    infix_notation,
    one_of,
)
from rapidfuzz.distance import DamerauLevenshtein

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
    """
    String comparer abstraction.

    The reason is to be able to change implementation.
    """

    def similarity(self, first, second):
        """Return string similarity in range 0 - 100%."""
        return int(100 * DamerauLevenshtein.normalized_similarity(first, second))


# Helper parsing objects
class RegexExpr:
    def __init__(self, tokens) -> None:
        self.expr = tokens[1]


class RangeExpr:
    def __init__(self, tokens) -> None:
        self.start = tokens[1]
        self.end = tokens[3]


OPERATOR_MAP = {
    ":": "substring",
    ":=": "exact",
    ":<": "lt",
    ":<=": "lte",
    ":>": "gt",
    ":>=": "gte",
}


def build_parser(term_expression: type[BaseTermExpr]):
    """Build parsing grammar."""
    # Booleans
    op_and = CaselessKeyword("AND")
    op_or = Optional(CaselessKeyword("OR"))
    op_not = CaselessKeyword("NOT")

    # Search operator
    operator = one_of(OPERATOR_MAP.keys())

    # Field name, explicitly exclude URL like patterns
    field = Regex(r"""(?!http|ftp|https|mailto)[a-zA-Z_]+""")

    # Match token
    word = Regex(r"""[^ \r\n\(\)]([^ \r\n'"]*[^ \r\n'"\)])?""")
    date = Word("0123456789:.-T")

    # Date range
    date_range = "[" + date + "to" + date + "]"
    date_range.add_parse_action(RangeExpr)

    # Match value
    regex_string = "r" + RawQuotedString('"')
    regex_string.add_parse_action(RegexExpr)
    string = regex_string | RawQuotedString("'") | RawQuotedString('"') | word

    # Single term, either field specific or not
    term = (field + operator + (date_range | string)) | string
    term.add_parse_action(term_expression)

    # Multi term with or without operator
    return Optional(
        infix_notation(
            term,
            [
                (
                    op_not,
                    1,
                    OpAssoc.RIGHT,
                ),
                (
                    op_and,
                    2,
                    OpAssoc.LEFT,
                ),
                (
                    op_or,
                    2,
                    OpAssoc.LEFT,
                ),
            ],
        )
    )


class BaseTermExpr:
    PLAIN_FIELDS: set[str] = set()
    NONTEXT_FIELDS: dict[str, str] = {}
    STRING_FIELD_MAP: dict[str, str] = {}
    EXACT_FIELD_MAP: dict[str, str] = {}
    enable_fulltext = True

    def __init__(self, tokens) -> None:
        if len(tokens) == 1:
            self.field = None
            self.operator = ":"
            self.match = tokens[0]
        else:
            self.field, self.operator, self.match = tokens
            self.fixup()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.field!r}, {self.operator!r}, {self.match!r}>"

    def fixup(self) -> None:
        # Avoid unwanted lt/gt searches on plain text fields
        if self.field in self.PLAIN_FIELDS and self.operator not in {":", ":="}:
            self.match = f"{self.operator[1:]}{self.match}"
            self.operator = ":"

    def convert_state(self, text):
        if text is None:
            return None
        if text.isdigit():
            return int(text)
        try:
            return STATE_NAMES[text]
        except KeyError as exc:
            raise ValueError(gettext("Unsupported state: {}").format(text)) from exc

    def convert_bool(self, text) -> bool:
        ltext = text.lower()
        if ltext in {"yes", "true", "on", "1"}:
            return True
        if ltext in {"no", "false", "off", "0"}:
            return False
        raise ValueError(f"Invalid boolean value: {text}")

    def convert_int(self, text):
        if isinstance(text, RangeExpr):
            return (
                self.convert_int(text.start),
                self.convert_int(text.end),
            )
        return int(text)

    def convert_id(self, text):
        if "," in text:
            return {self.convert_int(part) for part in text.split(",")}
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
            raise ValueError(gettext("Invalid timestamp: {}").format(error)) from error
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

    def field_name(self, field, suffix=None):
        if suffix is None:
            suffix = OPERATOR_MAP[self.operator]

        if field in self.EXACT_FIELD_MAP:
            # Change contains to exact, do not change other (for example regex)
            if suffix == "substring":
                suffix = "iexact"
            return f"{self.EXACT_FIELD_MAP[field]}__{suffix}"

        if not self.enable_fulltext and suffix == "substring":
            suffix = "icontains"

        if field in self.PLAIN_FIELDS:
            return f"{field}__{suffix}"
        if field in self.STRING_FIELD_MAP:
            return f"{self.STRING_FIELD_MAP[field]}__{suffix}"
        if field in self.NONTEXT_FIELDS:
            if suffix not in {"substring", "iexact"}:
                return f"{self.NONTEXT_FIELDS[field]}__{suffix}"
            return self.NONTEXT_FIELDS[field]
        raise ValueError(f"Unsupported field: {field}")

    def convert_non_field(self) -> NoReturn:
        raise NotImplementedError

    def as_query(self, context: dict):
        field = self.field
        match = self.match
        # Simple term based search
        if not field:
            return self.convert_non_field()

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
                raise ValueError(
                    gettext("Invalid regular expression: {}").format(error)
                ) from error
            from weblate.trans.models import Unit

            with transaction.atomic():
                try:
                    Unit.objects.annotate(test=Value("")).filter(
                        test__trgm_regex=match.expr
                    ).exists()
                except DataError as error:
                    raise ValueError(str(error)) from error
            return Q(**{self.field_name(field, "trgm_regex"): match.expr})

        if isinstance(match, tuple):
            start, end = match
            # Ranges
            if self.operator in {":", ":="}:
                query = Q(**{self.field_name(field, "range"): (start, end)})
            elif self.operator in {":>", ":>="}:
                query = Q(**{self.field_name(field, "gte"): start})
            else:
                query = Q(**{self.field_name(field, "lte"): end})

        elif isinstance(match, set):
            query = Q(**{self.field_name(field, "in"): match})
        else:
            # Generic query
            query = Q(**{self.field_name(field): match})

        return self.field_extra(field, query, match)

    def field_extra(self, field, query, match):
        return query

    def is_field(self, text, context: dict) -> NoReturn:
        raise ValueError(f"Unsupported is lookup: {text}")

    def has_field(self, text, context: dict) -> NoReturn:
        raise ValueError(f"Unsupported has lookup: {text}")


class UnitTermExpr(BaseTermExpr):
    PLAIN_FIELDS: set[str] = {"source", "target", "context", "note", "location"}
    NONTEXT_FIELDS: dict[str, str] = {
        "priority": "priority",
        "id": "id",
        "state": "state",
        "position": "position",
        "pending": "pending",
        "changed": "change__timestamp",
        "source_changed": "source_unit__last_updated",
        "change_time": "change__timestamp",
        "added": "timestamp",
        "change_action": "change__action",
    }
    STRING_FIELD_MAP: dict[str, str] = {
        "suggestion": "suggestion__target",
        "comment": "comment__comment",
        "resolved_comment": "comment__comment",
        "key": "context",
        "explanation": "source_unit__explanation",
    }
    EXACT_FIELD_MAP: dict[str, str] = {
        "check": "check__name",
        "dismissed_check": "check__name",
        "language": "translation__language__code",
        "component": "translation__component__slug",
        "project": "translation__component__project__slug",
        "changed_by": "change__author__username",
        "suggestion_author": "suggestion__user__username",
        "comment_author": "comment__user__username",
        "label": "source_unit__labels__name",
        "screenshot": "source_unit__screenshots__name",
    }

    def is_field(self, text, context: dict):
        if text in {"read-only", "readonly"}:
            return Q(state=STATE_READONLY)
        if text == "approved":
            return Q(state=STATE_APPROVED)
        if text in {"fuzzy", "needs-editing"}:
            return Q(state=STATE_FUZZY)
        if text == "translated":
            return Q(state__gte=STATE_TRANSLATED)
        if text == "untranslated":
            return Q(state__lt=STATE_TRANSLATED)
        if text == "pending":
            return Q(pending=True)

        return super().is_field(text, context)

    def has_field(self, text, context: dict):  # noqa: C901
        if text == "plural":
            return Q(source__search=PLURAL_SEPARATOR)
        if text == "suggestion":
            return Q(suggestion__isnull=False)
        if text == "explanation":
            return ~Q(source_unit__explanation="")
        if text == "note":
            return ~Q(note="")
        if text == "comment":
            return Q(comment__resolved=False)
        if text in {"resolved-comment", "resolved_comment"}:
            return Q(comment__resolved=True)
        if text in {"check", "failing-check", "failing_check"}:
            return Q(check__dismissed=False)
        if text in {
            "dismissed-check",
            "dismissed_check",
            "ignored-check",
            "ignored_check",
        }:
            return Q(check__dismissed=True)
        if text == "translation":
            return Q(state__gte=STATE_TRANSLATED)
        if text in {"variant", "shaping"}:
            return Q(variant__isnull=False)
        if text == "label":
            return Q(source_unit__labels__isnull=False) | Q(labels__isnull=False)
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

        return super().has_field(text, context)

    def convert_change_time(self, text):
        return self.convert_datetime(text)

    def convert_changed(self, text):
        return self.convert_datetime(text)

    def convert_source_changed(self, text):
        return self.convert_datetime(text)

    def convert_added(self, text):
        return self.convert_datetime(text)

    def convert_pending(self, text):
        return self.convert_bool(text)

    def convert_position(self, text):
        return self.convert_int(text)

    def convert_priority(self, text):
        return self.convert_int(text)

    def field_extra(self, field, query, match):
        from weblate.trans.models import Change

        if field in {"changed", "changed_by"}:
            return query & Q(change__action__in=Change.ACTIONS_CONTENT)
        if field == "check":
            return query & Q(check__dismissed=False)
        if field == "dismissed_check":
            return query & Q(check__dismissed=True)
        if field == "component":
            return query | Q(translation__component__name__icontains=match)
        if field == "label":
            return query | Q(labels__name__iexact=match)
        if field == "screenshot":
            return query | Q(screenshots__name__iexact=match)
        if field == "comment":
            return query & Q(comment__resolved=False)
        if field == "resolved_comment":
            return query & Q(comment__resolved=True)

        return super().field_extra(field, query, match)

    def convert_non_field(self):
        return (
            Q(source__substring=self.match)
            | Q(target__substring=self.match)
            | Q(context__substring=self.match)
        )


class UserTermExpr(BaseTermExpr):
    PLAIN_FIELDS: set[str] = {"username", "full_name"}
    NONTEXT_FIELDS: dict[str, str] = {
        "joined": "date_joined",
    }
    EXACT_FIELD_MAP: dict[str, str] = {
        "language": "profile__languages__code",
        "translates": "change__language__code",
    }
    enable_fulltext = False

    def convert_joined(self, text):
        return self.convert_datetime(text)

    def convert_non_field(self):
        return Q(username__icontains=self.match) | Q(full_name__icontains=self.match)

    def field_extra(self, field, query, match):
        if field == "translates":
            return query & Q(
                change__timestamp__date__gte=timezone.now().date() - timedelta(days=90)
            )

        return super().field_extra(field, query, match)

    def contributes_field(self, text, context: dict):
        from weblate.trans.models import Component

        if "/" in text:
            query = Q(
                change__component_id__in=list(
                    Component.objects.filter_by_path(text).values_list("id", flat=True)
                )
            )
        else:
            query = Q(change__project__slug__iexact=text)
        return query & Q(
            change__timestamp__date__gte=timezone.now().date() - timedelta(days=90)
        )


class SuperuserUserTermExpr(UserTermExpr):
    STRING_FIELD_MAP: dict[str, str] = {
        "email": "social_auth__verifiedemail__email",
    }

    def convert_non_field(self):
        return (
            Q(username__icontains=self.match)
            | Q(full_name__icontains=self.match)
            | Q(social_auth__verifiedemail__email__iexact=self.match)
        )

    def is_field(self, text, context: dict):
        if text == "active":
            return Q(is_active=True)
        if text == "bot":
            return Q(is_bot=True)
        if text == "superuser":
            return Q(is_superuser=True)

        return super().is_field(text, context)


PARSERS = {
    "unit": build_parser(UnitTermExpr),
    "user": build_parser(UserTermExpr),
    "superuser": build_parser(SuperuserUserTermExpr),
}


def parser_to_query(obj, context: dict):
    # Simple lookups
    if isinstance(obj, BaseTermExpr):
        return obj.as_query(context)

    # Operators
    operator = "AND"
    expressions = []
    for item in obj:
        if isinstance(item, str) and item.upper() in {"OR", "AND", "NOT"}:
            operator = item.upper()
            continue
        expressions.append(parser_to_query(item, context))

    if not expressions:
        return Q()

    if operator == "NOT":
        return ~expressions[0]
    if operator == "AND":
        return reduce(and_, expressions)
    return reduce(or_, expressions)


@lru_cache(maxsize=512)
def parse_string(text: str, parser: str):
    if "\x00" in text:
        raise ValueError("Invalid query string.")
    return PARSERS[parser].parse_string(text, parse_all=True)


def parse_query(text: str, parser: str = "unit", **context):
    parsed = parse_string(text, parser)
    return parser_to_query(parsed, context)
