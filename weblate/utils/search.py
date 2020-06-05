#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
from functools import lru_cache, reduce

import whoosh.qparser
import whoosh.qparser.dateparse
import whoosh.query
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from jellyfish import damerau_levenshtein_distance
from whoosh.fields import BOOLEAN, DATETIME, NUMERIC, TEXT, Schema
from whoosh.util.times import long_to_datetime

from weblate.trans.util import PLURAL_SEPARATOR
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


class QuotePlugin(whoosh.qparser.SingleQuotePlugin):
    """Single and double quotes to specify a term."""

    expr = r"(^|(?<=\W))['\"](?P<text>.*?)['\"](?=\s|\]|[)}]|$)"


class Exact(whoosh.query.Term):
    """Class for queries with exact operator."""

    pass


class ExactPlugin(whoosh.qparser.TaggingPlugin):
    """Exact match plugin to specify an exact term."""

    class ExactNode(whoosh.qparser.syntax.TextNode):
        qclass = Exact

        def r(self):
            return "Exact %r" % self.text

    expr = r"\=(^|(?<=\W))(['\"]?)(?P<text>.*?)\2(?=\s|\]|[)}]|$)"
    nodetype = ExactNode


class GtLtPlugin(whoosh.qparser.GtLtPlugin):
    """GtLt plugin taggin only after ":"."""

    def match(self, parser, text, pos):
        if pos == 0 or text[pos - 1] != ":":
            return None
        return super().match(parser, text, pos)


class DateParser(whoosh.qparser.dateparse.English):
    def setup(self):
        super().setup()
        # We prefer simple parser prior to datetime
        # This might not be necessary after following issue is fixed:
        # https://github.com/whoosh-community/whoosh/issues/552
        self.bundle.elements = (self.plusdate, self.simple, self.datetime)


class NumberField(NUMERIC):
    def to_bytes(self, x, shift=0):
        return int(x)


class StateField(NumberField):
    def parse_query(self, fieldname, qstring, boost=1.0):
        return super().parse_query(fieldname, state_to_int(qstring), boost)

    def parse_range(self, fieldname, start, end, startexcl, endexcl, boost=1.0):
        return super().parse_range(
            fieldname, state_to_int(start), state_to_int(end), startexcl, endexcl, boost
        )


def state_to_int(text):
    if text is None:
        return None
    try:
        return STATE_NAMES[text]
    except KeyError:
        raise ValueError(_("Unsupported state: {}").format(text))


class QueryParser(whoosh.qparser.QueryParser):
    """Weblate query parser, differences to Whoosh default.

    - no phrase plugin
    - <> operators support
    - double and single quotes behave identical
    - multifield lookup for unspecified terms
    """

    def __init__(self):
        # Define fields for parsing
        fields = {
            # Unit fields
            "source": TEXT,
            "target": TEXT,
            "context": TEXT,
            "key": TEXT,
            "note": TEXT,
            "location": TEXT,
            "priority": NumberField,
            "added": DATETIME,
            "state": StateField,
            "pending": BOOLEAN,
            "has": TEXT,
            "is": TEXT,
            # Language
            "language": TEXT,
            # Change fields
            "changed": DATETIME,
            "changed_by": TEXT,
            # Unit data
            "check": TEXT,
            "dismissed_check": TEXT,
            "suggestion": TEXT,
            "suggestion_author": TEXT,
            "comment": TEXT,
            "comment_author": TEXT,
            "label": TEXT,
        }
        schema = Schema(**fields)

        # List of plugins
        plugins = [
            whoosh.qparser.WhitespacePlugin(),
            QuotePlugin(),
            whoosh.qparser.FieldsPlugin(),
            whoosh.qparser.RangePlugin(),
            GtLtPlugin(),
            ExactPlugin(),
            whoosh.qparser.RegexPlugin(),
            whoosh.qparser.GroupPlugin(),
            whoosh.qparser.OperatorsPlugin(),
            whoosh.qparser.dateparse.DateParserPlugin(dateparser=DateParser()),
            whoosh.qparser.MultifieldPlugin(["source", "target", "context"]),
        ]
        super().__init__(None, schema, plugins=plugins)

    def term_query(
        self, fieldname, text, termclass, boost=1.0, tokenize=True, removestops=True
    ):
        if self.schema and fieldname in self.schema:
            if isinstance(self.schema[fieldname], TEXT):
                return termclass(fieldname, text, boost=boost)
        return super().term_query(
            fieldname, text, termclass, boost, tokenize, removestops
        )


PARSER = QueryParser()

PLAIN_FIELDS = ("source", "target", "context", "note", "location")
FIELD_MAP = {"changed": "change__timestamp", "added": "timestamp"}
STRING_FIELD_MAP = {"suggestion": "suggestion__target", "comment": "comment__comment"}
STRING_FIELD_MAP = {"key": "context"}
EXACT_FIELD_MAP = {
    "check": "check__check",
    "dismissed_check": "check__check",
    "language": "translation__language__code",
    "changed_by": "change__author__username",
    "suggestion_author": "suggestion__user__username",
    "comment_author": "comment__user__username",
    "label": "labels__name",
}


def field_name(field, suffix="substring"):
    if field in FIELD_MAP:
        return FIELD_MAP[field]
    if field in PLAIN_FIELDS:
        return "{}__{}".format(field, suffix)
    if field in STRING_FIELD_MAP:
        return "{}__{}".format(STRING_FIELD_MAP[field], suffix)
    if field in EXACT_FIELD_MAP:
        # Change contains to exact, do not change other (for example regex)
        if suffix == "substring":
            suffix = "iexact"
        return "{}__{}".format(EXACT_FIELD_MAP[field], suffix)
    return field


def field_extra(field, query):
    from weblate.trans.models import Change

    if field in {"changed", "changed_by"}:
        return query & Q(change__action__in=Change.ACTIONS_CONTENT)
    if field == "check":
        return query & Q(check__dismissed=False)
    if field == "dismissed_check":
        return query & Q(check__dismissed=True)
    return query


def range_sql(field, start, end, startexcl, endexcl, conv=int):
    def range_lookup(field, op, value):
        return {"{}__{}".format(field_name(field), op): conv(value)}

    gte = "gt" if startexcl else "gte"
    lte = "lt" if endexcl else "lte"

    if start is not None and end is not None:
        return Q(**range_lookup(field, gte, start)) & Q(**range_lookup(field, lte, end))
    if start is not None:
        return Q(**range_lookup(field, gte, start))
    return Q(**range_lookup(field, lte, end))


def has_sql(text):
    if text == "plural":
        return Q(source__contains=PLURAL_SEPARATOR)
    if text == "suggestion":
        return Q(suggestion__isnull=False)
    if text == "comment":
        return Q(comment__resolved=False)
    if text in ("resolved-comment", "resolved_comment"):
        return Q(comment__resolved=True)
    if text in ("check", "failing-check", "failing_check"):
        return Q(check__dismissed=False)
    if text in ("dismissed-check", "dismissed_check", "ignored-check", "ignored_check"):
        return Q(check__dismissed=True)
    if text == "translation":
        return Q(state__gte=STATE_TRANSLATED)
    if text in ("variant", "shaping"):
        return Q(variant__isnull=False)
    if text == "label":
        return Q(labels__isnull=False)
    if text == "context":
        return ~Q(context="")
    if text == "screenshot":
        return Q(screenshots__isnull=False)
    if text == "flags":
        return ~Q(extra_flags="")

    raise ValueError("Unsupported has lookup: {}".format(text))


def is_sql(text):
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

    raise ValueError("Unsupported is lookup: {}".format(text))


def exact_sql(field, text):
    return Q(**{field_name(field, "iexact"): text})


def query_sql(obj):
    if isinstance(obj, whoosh.query.And):
        return reduce(
            lambda x, y: x & y,
            (query_sql(q) for q in obj.subqueries if q != whoosh.query.NullQuery),
        )
    if isinstance(obj, whoosh.query.Or):
        return reduce(
            lambda x, y: x | y,
            (query_sql(q) for q in obj.subqueries if q != whoosh.query.NullQuery),
        )
    if isinstance(obj, whoosh.query.Not):
        return ~query_sql(obj.query)
    if isinstance(obj, Exact):
        return exact_sql(obj.fieldname, obj.text)
    if isinstance(obj, whoosh.query.Term):
        if obj.fieldname == "has":
            return has_sql(obj.text)
        if obj.fieldname == "is":
            return is_sql(obj.text)
        return field_extra(obj.fieldname, Q(**{field_name(obj.fieldname): obj.text}))
    if isinstance(obj, whoosh.query.DateRange):
        return field_extra(
            obj.fieldname,
            range_sql(
                obj.fieldname,
                obj.startdate,
                obj.enddate,
                obj.startexcl,
                obj.endexcl,
                timezone.make_aware,
            ),
        )
    if isinstance(obj, whoosh.query.NumericRange):
        if obj.fieldname in {"added", "changed"}:
            return field_extra(
                obj.fieldname,
                range_sql(
                    obj.fieldname,
                    long_to_datetime(obj.start),
                    long_to_datetime(obj.end),
                    obj.startexcl,
                    obj.endexcl,
                    timezone.make_aware,
                ),
            )
        return range_sql(obj.fieldname, obj.start, obj.end, obj.startexcl, obj.endexcl)
    if isinstance(obj, whoosh.query.Regex):
        try:
            re.compile(obj.text)
            return Q(**{field_name(obj.fieldname, "regex"): obj.text})
        except re.error as error:
            raise ValueError(_("Invalid regular expression: {}").format(error))

    if obj == whoosh.query.NullQuery:
        return Q()
    raise ValueError("Unsupported: {!r}".format(obj))


@lru_cache(maxsize=512)
def parse_query(text):
    if "\x00" in text:
        raise ValueError("Invalid query string.")
    return query_sql(PARSER.parse(text))
