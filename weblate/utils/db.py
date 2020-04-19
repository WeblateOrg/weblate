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
"""Database specific code to extend Django."""

from django.contrib.postgres.search import (
    SearchVector,
    SearchVectorExact,
    SearchVectorField,
)
from django.db import models, router
from django.db.models.deletion import Collector
from django.db.models.lookups import PatternLookup

ESCAPED = frozenset(".\\+*?[^]$(){}=!<>|:-")


class PostgreSQLSearchVector(SearchVector):
    def as_sql(self, compiler, connection, function=None, template=None):
        return super(SearchVector, self).as_sql(
            compiler,
            connection,
            function=function,
            template="%(function)s('english'::regconfig, %(expressions)s)",
        )


class PostgreSQLSearchLookup(SearchVectorExact):
    lookup_name = "search"

    def process_lhs(self, qn, connection):
        if not isinstance(self.lhs.output_field, SearchVectorField):
            self.lhs = PostgreSQLSearchVector(self.lhs)
        lhs, lhs_params = super().process_lhs(qn, connection)
        return lhs, lhs_params


class MySQLSearchLookup(models.Lookup):
    lookup_name = "search"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return "MATCH (%s) AGAINST (%s IN NATURAL LANGUAGE MODE)" % (lhs, rhs), params


class MySQLSubstringLookup(MySQLSearchLookup):
    lookup_name = "substring"


class PostgreSQLSubstringLookup(PatternLookup):
    """
    Case insensitive substring lookup.

    This is essentially same as icontains in Django, but utilizes ILIKE
    operator which can use pg_trgm index.
    """

    lookup_name = "substring"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return "%s ILIKE %s" % (lhs, rhs), params


def table_has_row(connection, table, rowname):
    """Check whether actual table has row."""
    with connection.cursor() as cursor:
        table_description = connection.introspection.get_table_description(
            cursor, table
        )
        for row in table_description:
            if row.name == rowname:
                return True
    return False


def re_escape(pattern):
    """Escape for use in database regexp match.

    This is based on re.escape, but that one escapes too much.
    """
    string = list(pattern)
    for i, char in enumerate(pattern):
        if char == "\000":
            string[i] = "\\000"
        elif char in ESCAPED:
            string[i] = "\\" + char
    return "".join(string)


class FastCollector(Collector):
    """
    Fast delete collector skipping some signals.

    It allows fast deletion for models flagged with weblate_unsafe_delete.

    This is needed as check removal triggers check run and that can
    create new checks for just removed units.
    """

    def can_fast_delete(self, objs, from_field=None):
        if hasattr(objs, "model") and getattr(
            objs.model, "weblate_unsafe_delete", False
        ):
            return True
        return super().can_fast_delete(objs, from_field)


class FastDeleteMixin:
    """Model mixin to use FastCollector."""

    def delete(self, using=None, keep_parents=False):
        """Copy of Django delete with changed collector."""
        using = using or router.db_for_write(self.__class__, instance=self)
        collector = FastCollector(using=using)
        collector.collect([self], keep_parents=keep_parents)
        return collector.delete()
