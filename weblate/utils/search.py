# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import re
from functools import reduce

import whoosh.qparser
import whoosh.qparser.dateparse
import whoosh.query
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import ugettext as _
from jellyfish import damerau_levenshtein_distance
from jellyfish._jellyfish import (
    damerau_levenshtein_distance as py_damerau_levenshtein_distance,
)
from whoosh.fields import BOOLEAN, DATETIME, NUMERIC, TEXT, Schema

from weblate.utils.state import STATE_NAMES


class Comparer(object):
    """String comparer abstraction.

    The reason is to be able to change implementation."""

    def similarity(self, first, second):
        """Returns string similarity in range 0 - 100%."""
        try:
            try:
                distance = damerau_levenshtein_distance(first, second)
            except ValueError:
                # Needed on Python 2 only (actually jellyfish < 0.7.2)
                distance = py_damerau_levenshtein_distance(first, second)

            return int(
                100 * (1.0 - (float(distance) / max(len(first), len(second), 1)))
            )
        except MemoryError:
            # Too long string, mark them as not much similar
            return 50


class QuotePlugin(whoosh.qparser.SingleQuotePlugin):
    """Single and double quotes to specify a term"""

    expr = r"(^|(?<=\W))['\"](?P<text>.*?)['\"](?=\s|\]|[)}]|$)"


class GtLtPlugin(whoosh.qparser.GtLtPlugin):
    """GtLt plugin taggin only after :"""

    def match(self, parser, text, pos):
        if pos == 0 or text[pos - 1] != ":":
            return None
        return super(GtLtPlugin, self).match(parser, text, pos)


class DateParser(whoosh.qparser.dateparse.English):
    def setup(self):
        super(DateParser, self).setup()
        # We prefer simple parser prior to datetime
        # This might not be necessary after following issue is fixed:
        # https://github.com/whoosh-community/whoosh/issues/552
        self.bundle.elements = (self.plusdate, self.simple, self.datetime)


class StateField(NUMERIC):
    def parse_query(self, fieldname, qstring, boost=1.0):
        return super(StateField, self).parse_query(
            fieldname, state_to_int(qstring), boost
        )

    def parse_range(self, fieldname, start, end, startexcl, endexcl, boost=1.0):
        return super(StateField, self).parse_range(
            fieldname, state_to_int(start), state_to_int(end), startexcl, endexcl, boost
        )

    def to_bytes(self, x, shift=0):
        return int(x)


def state_to_int(text):
    try:
        return STATE_NAMES[text]
    except KeyError:
        return text


class QueryParser(whoosh.qparser.QueryParser):
    """
    Weblate query parser, differences to Whoosh default

    - no phrase plugin
    - <> operators support
    - double and single quotes behave identical
    - multifield lookup for unspecified terms
    """

    def __init__(self):
        # Define fields for parsing
        schema = Schema(
            # Unit fields
            source=TEXT,
            target=TEXT,
            context=TEXT,
            comment=TEXT,
            location=TEXT,
            priority=NUMERIC,
            state=StateField,
            pending=BOOLEAN,
            has_suggestion=BOOLEAN,
            has_comment=BOOLEAN,
            has_failing_check=BOOLEAN,
            # Language
            language=TEXT,
            # Change fields
            changed=DATETIME,
            changed_by=TEXT,
        )
        # Features to implement and corresponding blockers
        # - created timestamp, https://github.com/WeblateOrg/weblate/issues/2831
        # - unitdata lookups, https://github.com/WeblateOrg/weblate/issues/3007

        # List of plugins
        plugins = [
            whoosh.qparser.WhitespacePlugin(),
            QuotePlugin(),
            whoosh.qparser.FieldsPlugin(),
            whoosh.qparser.RangePlugin(),
            GtLtPlugin(),
            whoosh.qparser.RegexPlugin(),
            whoosh.qparser.GroupPlugin(),
            whoosh.qparser.OperatorsPlugin(),
            whoosh.qparser.dateparse.DateParserPlugin(dateparser=DateParser()),
            whoosh.qparser.MultifieldPlugin(["source", "target", "context"]),
        ]
        super(QueryParser, self).__init__(None, schema, plugins=plugins)

    def term_query(
        self, fieldname, text, termclass, boost=1.0, tokenize=True, removestops=True
    ):
        if self.schema and fieldname in self.schema:
            if isinstance(self.schema[fieldname], TEXT):
                return termclass(fieldname, text, boost=boost)
        return super(QueryParser, self).term_query(
            fieldname, text, termclass, boost, tokenize, removestops
        )


PARSER = QueryParser()


def field_name(field, suffix="icontains"):
    if field == "changed":
        return "change__timestamp"
    if field == "changed_by":
        return "change__author__username"
    if field == "language":
        return "translation__language__code"
    if field in ("source", "target", "context", "comment", "location"):
        return "{}__{}".format(field, suffix)
    return field


def field_extra(field, query):
    from weblate.trans.models import Change

    if field in {"changed", "changed_by"}:
        return query & Q(change__action__in=Change.ACTIONS_CONTENT)
    return query


def range_sql(field, start, end, conv=int):
    def range_lookup(field, op, value):
        return {"{}__{}".format(field_name(field), op): conv(value)}

    if start and end:
        return Q(**range_lookup(field, "gte", start)) & Q(
            **range_lookup(field, "lte", end)
        )
    if start:
        return Q(**range_lookup(field, "gte", start))
    return Q(**range_lookup(field, "lte", end))


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
    if isinstance(obj, whoosh.query.Term):
        return Q(**{field_name(obj.fieldname): obj.text})
    if isinstance(obj, whoosh.query.DateRange):
        return field_extra(
            obj.fieldname,
            range_sql(obj.fieldname, obj.startdate, obj.enddate, timezone.make_aware),
        )
    if isinstance(obj, whoosh.query.NumericRange):
        return range_sql(obj.fieldname, obj.start, obj.end)
    if isinstance(obj, whoosh.query.Regex):
        try:
            re.compile(obj.text)
            return Q(**{field_name(obj.fieldname, "regex"): obj.text})
        except re.error as error:
            raise ValueError(_("Invalid regular expression: {}").format(error))

    if obj == whoosh.query.NullQuery:
        return Q()
    raise ValueError("Unsupported: {!r}".format(obj))


def parse_query(text):
    return query_sql(PARSER.parse(text))
