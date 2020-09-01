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

from django.db import models, router
from django.db.models import Case, IntegerField, Sum, When
from django.db.models.deletion import Collector
from django.db.models.lookups import PatternLookup

ESCAPED = frozenset(".\\+*?[^]$(){}=!<>|:-")


def conditional_sum(value=1, **cond):
    """Wrapper to generate SUM on boolean/enum values."""
    return Sum(Case(When(then=value, **cond), default=0, output_field=IntegerField()))


class PostgreSQLSearchLookup(PatternLookup):
    lookup_name = "search"

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return "%s %%%% %s = true" % (lhs, rhs), params


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

    @staticmethod
    def is_weblate_unsafe(model):
        return getattr(model, "weblate_unsafe_delete", False)

    def can_fast_delete(self, objs, from_field=None):
        if hasattr(objs, "model") and self.is_weblate_unsafe(objs.model):
            return True
        return super().can_fast_delete(objs, from_field)

    def delete(self):
        from weblate.trans.models import Suggestion, Vote

        fast_deletes = []
        for item in self.fast_deletes:
            if item.model is Suggestion:
                fast_deletes.append(Vote.objects.filter(suggestion__in=item))
            fast_deletes.append(item)
        self.fast_deletes = fast_deletes
        return super().delete()


class FastDeleteMixin:
    """Model mixin to use FastCollector."""

    def delete(self, using=None, keep_parents=False):
        """Copy of Django delete with changed collector."""
        using = using or router.db_for_write(self.__class__, instance=self)
        collector = FastCollector(using=using)
        collector.collect([self], keep_parents=keep_parents)
        return collector.delete()
