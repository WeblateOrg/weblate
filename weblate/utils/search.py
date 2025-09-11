# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import threading
from datetime import datetime
from functools import lru_cache, reduce
from itertools import chain
from operator import and_, or_
from typing import TYPE_CHECKING, Any, Literal, cast, overload

from dateutil.parser import ParserError
from dateutil.parser import parse as dateutil_parse
from django.db import transaction
from django.db.models import Count, F, Q, Value
from django.db.utils import DataError, OperationalError
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext
from pyparsing import (
    CaselessKeyword,
    OpAssoc,
    Optional,
    ParseResults,
    Regex,
    Word,
    alphanums,
    infix_notation,
    one_of,
)

from weblate.checks.parser import RawQuotedString
from weblate.lang.models import Language
from weblate.trans.models import Category, Component, Project, Translation
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.db import re_escape, using_postgresql
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_FUZZY,
    STATE_NAMES,
    STATE_READONLY,
    STATE_TRANSLATED,
)
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Expression
    from pyparsing import (
        ParserElement,
    )


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


def build_parser(term_expression: type[BaseTermExpr]) -> ParserElement:
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
    date = Word(alphanums + ":._-")

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

    def convert_state(self, text: str) -> int | None:
        if text is None:
            return None
        if text.isdigit():
            return int(text)
        try:
            return STATE_NAMES[text]
        except KeyError as exc:
            raise ValueError(gettext("Unsupported state: {}").format(text)) from exc

    def convert_bool(self, text: str) -> bool:
        ltext = text.lower()
        if ltext in {"yes", "true", "on", "1"}:
            return True
        if ltext in {"no", "false", "off", "0"}:
            return False
        msg = f"Invalid boolean value: {text}"
        raise ValueError(msg)

    @overload
    def convert_int(self, text: RangeExpr) -> tuple[int, int]: ...
    @overload
    def convert_int(self, text: str) -> int: ...
    def convert_int(self, text):
        if isinstance(text, RangeExpr):
            return (
                self.convert_int(text.start),
                self.convert_int(text.end),
            )
        return int(text)

    def convert_id(self, text: str) -> int | set[int]:
        if "," in text:
            return {self.convert_int(part) for part in text.split(",")}
        return self.convert_int(text)

    @overload
    def convert_datetime(
        self,
        text: RangeExpr,
    ) -> tuple[datetime, datetime]: ...
    @overload
    def convert_datetime(
        self,
        text: str,
    ) -> datetime: ...
    def convert_datetime(self, text):
        if isinstance(text, RangeExpr):
            return (
                self.date_parse(text.start, hour=0, minute=0, second=0, microsecond=0),
                self.date_parse(
                    text.end, hour=23, minute=59, second=59, microsecond=999999
                ),
            )
        if text.isdigit() and len(text) == 4:
            tzinfo = timezone.get_current_timezone()
            year = int(text)
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

        return self.date_parse(text)

    def get_day_range(self, timestamp: datetime) -> tuple[datetime, datetime]:
        return (
            timestamp.replace(hour=0, minute=0, second=0, microsecond=0),
            timestamp.replace(hour=23, minute=59, second=59, microsecond=999999),
        )

    @overload
    def date_parse_human(
        self,
        text: str,
        hour: None = None,
        minute: None = None,
        second: None = None,
        microsecond: None = None,
    ) -> datetime | tuple[datetime, datetime]: ...
    @overload
    def date_parse_human(
        self,
        text: str,
        hour: int,
        minute: int,
        second: int,
        microsecond: int,
    ) -> datetime: ...
    def date_parse_human(
        self,
        text,
        hour=None,
        minute=None,
        second=None,
        microsecond=None,
    ):
        # Lazily import as this can be expensive
        from dateparser.date import DateDataParser

        # Custom RELATIVE_BASE allows to base "1 day ago" from the midnight instead
        # of the current time
        parser = DateDataParser(
            locales=["en"],
            settings={
                "RELATIVE_BASE": timezone.now().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            },
        )

        # Attempts to parse the text using dateparser
        # If the text is unparsable it will return None
        data = parser.get_date_data(text)

        date_obj: datetime | None = data.date_obj

        if date_obj is None:
            msg = "Could not parse timestamp"
            raise ValueError(msg)

        # Always include timezone
        if date_obj.tzinfo is None:
            date_obj = date_obj.replace(tzinfo=timezone.get_current_timezone())

        if data.period == "day":
            if (
                hour is not None
                and minute is not None
                and second is not None
                and microsecond is not None
            ):
                # Replace timestamp when parsing range
                return date_obj.replace(
                    hour=hour,
                    minute=minute,
                    second=second,
                    microsecond=microsecond,
                    tzinfo=timezone.get_current_timezone(),
                )
            # Create one day range from date only
            if (
                date_obj.hour == 0
                and date_obj.minute == 0
                and date_obj.second == 0
                and date_obj.microsecond == 0
            ):
                return self.get_day_range(date_obj)

        return date_obj

    @overload
    def date_parse(
        self,
        text: str,
        hour: None = None,
        minute: None = None,
        second: None = None,
        microsecond: None = None,
    ) -> datetime | tuple[datetime, datetime]: ...
    @overload
    def date_parse(
        self,
        text: str,
        hour: int,
        minute: int,
        second: int,
        microsecond: int,
    ) -> datetime: ...
    def date_parse(
        self,
        text,
        hour=None,
        minute=None,
        second=None,
        microsecond=None,
    ):
        result: datetime | None

        default = timezone.now()
        if hour is None or minute is None or second is None or microsecond is None:
            # Here we inject 5:55:55 time and if that was not changed
            # during parsing, we assume it was not specified while
            # generating the query
            default = default.replace(hour=5, minute=5, second=5, microsecond=5)
        else:
            # Apply real defaults
            default = default.replace(
                hour=hour, minute=minute, second=second, microsecond=microsecond
            )

        try:
            result = dateutil_parse(text, default=default)
        except ParserError:
            result = None

        if not result:
            return self.date_parse_human(
                text, hour=hour, minute=minute, second=second, microsecond=microsecond
            )
            msg = "Could not parse timestamp"
            raise ValueError(msg)

        if (
            hour is None
            and result.hour == 5
            and result.minute == 5
            and result.second == 5
            and result.microsecond == 5
        ):
            return (
                result.replace(hour=0, minute=0, second=0, microsecond=0),
                result.replace(hour=23, minute=59, second=59, microsecond=999999),
            )

        return result

    def convert_change_action(self, text: str) -> int:
        from weblate.trans.models import Change

        try:
            return Change.ACTION_NAMES[text]
        except KeyError:
            return Change.ACTION_STRINGS[text]

    def convert_change_time(self, text: str) -> datetime | tuple[datetime, datetime]:
        return self.convert_datetime(text)

    def field_name(self, field: str, suffix: str | None = None) -> str:
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
        msg = f"Unsupported field: {field}"
        raise ValueError(msg)

    def convert_non_field(self) -> Q:
        raise NotImplementedError

    def as_query(self, context: dict) -> Q:
        field = self.field
        match = self.match
        # Simple term based search
        if not field:
            return self.convert_non_field()

        # Field specific code
        field_method: Callable[[str, dict], Q] | None = cast(
            "Callable[[str, dict], Q] | None",
            getattr(self, f"{field}_field", None),
        )
        if field_method is not None:
            return field_method(match, context)

        # Field conversion
        convert_method = getattr(self, f"convert_{field}", None)
        if convert_method is not None:
            match = convert_method(match)

        if isinstance(match, RegexExpr):
            # Regular expression
            from weblate.trans.models import Unit

            with transaction.atomic():
                try:
                    Unit.objects.annotate(test=Value("")).filter(
                        test__trgm_regex=match.expr
                    ).exists()
                except (DataError, OperationalError) as error:
                    # PostgreSQL raises DataError, MySQL OperationalError
                    raise ValueError(
                        gettext("Invalid regular expression: {}").format(error)
                    ) from error
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

    def get_annotations(self, context: dict) -> dict[str, Expression]:
        return {}

    def field_extra(self, field: str, query: Q, match: Any) -> Q:  # noqa: ANN401
        return query

    def is_field(self, text: str, context: dict) -> Q:
        msg = f"Unsupported is lookup: {text}"
        raise ValueError(msg)

    def has_field(self, text: str, context: dict) -> Q:
        msg = f"Unsupported has lookup: {text}"
        raise ValueError(msg)


class UnitTermExpr(BaseTermExpr):
    PLAIN_FIELDS: set[str] = {"source", "target", "context", "note", "location"}
    NONTEXT_FIELDS: dict[str, str] = {
        "priority": "priority",
        "id": "id",
        "state": "state",
        "source_state": "source_unit__state",
        "position": "position",
        "pending": "pending_changes__isnull",
        "changed": "change__timestamp",
        "source_changed": "source_unit__last_updated",
        "last_changed": "last_updated",
        "change_time": "change__timestamp",
        "added": "timestamp",
        "change_action": "change__action",
        "labels_count": "labels_count",
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
        "project": "translation__component__project__slug",
        "changed_by": "change__author__username",
        "suggestion_author": "suggestion__user__username",
        "comment_author": "comment__user__username",
        "label": "source_unit__labels__name",
        "screenshot": "source_unit__screenshots__name",
    }

    def is_field(self, text: str, context: dict) -> Q:
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
            return Q(pending_changes__isnull=False)

        return super().is_field(text, context)

    def has_field(self, text: str, context: dict) -> Q:  # noqa: C901
        if text == "plural":
            return Q(source__search=PLURAL_SEPARATOR)
        if text == "suggestion":
            return Q(suggestion__isnull=False)
        if text == "explanation":
            return ~Q(source_unit__explanation="")
        if text == "location":
            return ~Q(location="")
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
            return Q(defined_variants__isnull=False) | (
                ~Q(variant__variant_regex="")
                & Q(context__regex=F("variant__variant_regex"))
            )
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

    def convert_source_state(self, text: str) -> int | None:
        return self.convert_state(text)

    def component_field(self, text: str, context: dict) -> Q:
        if self.operator == ":=":
            return Q(translation__component__slug__iexact=text) | Q(
                translation__component__name__iexact=text
            )
        return Q(translation__component__slug__icontains=text) | Q(
            translation__component__name__icontains=text
        )

    def path_field(self, text: str, context: dict) -> Q:
        try:
            obj = parse_path(
                None,
                text.split("/"),
                (
                    Translation,
                    Component,
                    Project,
                    ProjectLanguage,
                    Category,
                    CategoryLanguage,
                    Language,
                ),
            )
        except Http404:
            return Q(translation=None)

        if isinstance(obj, Translation):
            return Q(translation=obj)
        if isinstance(obj, Component):
            return Q(translation__component=obj)
        if isinstance(obj, Project):
            return Q(translation__component__project=obj)
        if isinstance(obj, ProjectLanguage):
            return Q(translation__component__project=obj.project) & Q(
                translation__language=obj.language
            )
        if isinstance(obj, Category):
            return Q(translation__component_id__in=obj.all_component_ids)
        if isinstance(obj, CategoryLanguage):
            return Q(translation__component_id__in=obj.category.all_component_ids) & Q(
                translation__language=obj.language
            )
        if isinstance(obj, Language):
            return Q(translation__language=obj)
        msg = f"Unsupported path lookup: {obj}"
        raise TypeError(msg)

    def pending_field(self, text: str, context: dict) -> Q:
        boolean_value = self.convert_bool(text)
        return Q(pending_changes__isnull=not boolean_value)

    def convert_changed(self, text: str) -> datetime | tuple[datetime, datetime]:
        return self.convert_datetime(text)

    def convert_source_changed(self, text: str) -> datetime | tuple[datetime, datetime]:
        return self.convert_datetime(text)

    def convert_last_changed(self, text: str) -> datetime | tuple[datetime, datetime]:
        return self.convert_datetime(text)

    def convert_added(self, text: str) -> datetime | tuple[datetime, datetime]:
        return self.convert_datetime(text)

    def convert_position(self, text: str) -> int:
        return self.convert_int(text)

    def convert_priority(self, text: str) -> int:
        return self.convert_int(text)

    def convert_labels_count(self, text: str) -> int:
        return self.convert_int(text)

    def field_extra(self, field: str, query: Q, match: Any) -> Q:  # noqa: ANN401
        from weblate.trans.models import Change

        if field in {"changed", "changed_by"}:
            return query & Q(change__action__in=Change.ACTIONS_CONTENT)
        if field == "check":
            return query & Q(check__dismissed=False)
        if field == "dismissed_check":
            return query & Q(check__dismissed=True)
        if field == "label":
            return query | Q(labels__name__iexact=match)
        if field == "screenshot":
            return query | Q(screenshots__name__iexact=match)
        if field == "comment":
            return query & Q(comment__resolved=False)
        if field == "resolved_comment":
            return query & Q(comment__resolved=True)

        return super().field_extra(field, query, match)

    def convert_non_field(self) -> Q:
        return (
            Q(source__substring=self.match)
            | Q(target__substring=self.match)
            | Q(context__substring=self.match)
        )

    def get_annotations(self, context: dict) -> dict[str, Expression]:
        if self.field == "labels_count":
            return {"labels_count": Count("source_unit__labels") + Count("labels")}
        return super().get_annotations(context)


class UserTermExpr(BaseTermExpr):
    PLAIN_FIELDS: set[str] = {"username", "full_name"}
    NONTEXT_FIELDS: dict[str, str] = {
        "joined": "date_joined",
        "change_time": "change__timestamp",
        "change_action": "change__action",
    }
    EXACT_FIELD_MAP: dict[str, str] = {
        "language": "profile__languages__code",
        "translates": "change__language__code",
    }
    enable_fulltext = False

    def convert_joined(self, text: str) -> datetime | tuple[datetime, datetime]:
        return self.convert_datetime(text)

    def convert_non_field(self) -> Q:
        return Q(username__icontains=self.match) | Q(full_name__icontains=self.match)

    def contributes_field(self, text: str, context: dict) -> Q:
        from weblate.trans.models import Component

        if "/" not in text:
            return Q(change__project__slug__iexact=text)
        return Q(
            change__component_id__in=list(
                Component.objects.filter_by_path(text).values_list("id", flat=True)
            )
        )


class SuperuserUserTermExpr(UserTermExpr):
    STRING_FIELD_MAP: dict[str, str] = {
        "email": "social_auth__verifiedemail__email",
    }

    def convert_non_field(self) -> Q:
        return (
            Q(username__icontains=self.match)
            | Q(full_name__icontains=self.match)
            | Q(social_auth__verifiedemail__email__iexact=self.match)
        )

    def is_field(self, text: str, context: dict) -> Q:
        if text == "active":
            return Q(is_active=True)
        if text == "bot":
            return Q(is_bot=True)
        if text == "superuser":
            return Q(is_superuser=True)

        return super().is_field(text, context)


PARSERS: dict[Literal["unit", "user", "superuser"], ParserElement] = {
    "unit": build_parser(UnitTermExpr),
    "user": build_parser(UserTermExpr),
    "superuser": build_parser(SuperuserUserTermExpr),
}
PARSER_LOCK = threading.Lock()


def parser_to_query(obj: ParseResults | BaseTermExpr, context: dict) -> Q:
    # Simple lookups
    if isinstance(obj, BaseTermExpr):
        return obj.as_query(context)

    # Operators
    operator = ""
    expressions: list[Q] = []
    was_operator = False
    for item in obj:
        if isinstance(item, str) and (current := item.upper()) in {"OR", "AND", "NOT"}:
            if operator and current != operator:
                msg = "Mixed operators!"
                raise ValueError(msg)
            operator = current
            was_operator = True
            continue
        if not was_operator and expressions:
            # Implicit AND
            expressions[-1] &= parser_to_query(item, context)
        else:
            expressions.append(parser_to_query(item, context))
        was_operator = False

    if not expressions:
        return Q()

    if operator == "NOT":
        return ~expressions[0]
    if operator == "AND":
        return reduce(and_, expressions)
    return reduce(or_, expressions)


def parser_annotations(
    obj: ParseResults | BaseTermExpr, context: dict
) -> dict[str, Expression]:
    result: dict[str, Expression] = {}
    if isinstance(obj, BaseTermExpr):
        result.update(obj.get_annotations(context))
    else:
        for item in obj:
            if isinstance(item, (BaseTermExpr, ParseResults)):
                result.update(parser_annotations(item, context))
    return result


@lru_cache(maxsize=512)
def parse_string(
    text: str, parser: Literal["unit", "user", "superuser"]
) -> ParseResults:
    if "\x00" in text:
        msg = "Invalid query string."
        raise ValueError(msg)
    with PARSER_LOCK:
        return PARSERS[parser].parse_string(text, parse_all=True)


def parse_query(
    text: str, parser: Literal["unit", "user", "superuser"] = "unit", **context
) -> tuple[Q, dict[str, Expression]]:
    parsed = parse_string(text, parser)
    return parser_to_query(parsed, context), parser_annotations(parsed, context)
