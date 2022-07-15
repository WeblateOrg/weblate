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
"""Database specific code to extend Django."""

from django.db import connection, models
from django.db.models import Case, IntegerField, Sum, When
from django.db.models.lookups import PatternLookup

ESCAPED = frozenset(".\\+*?[^]$(){}=!<>|:-")

PG_TRGM = "CREATE INDEX {0}_{1}_fulltext ON trans_{0} USING GIN ({1} gin_trgm_ops)"
PG_DROP = "DROP INDEX {0}_{1}_fulltext"

MY_FTX = "CREATE FULLTEXT INDEX {0}_{1}_fulltext ON trans_{0}({1})"
MY_DROP = "ALTER TABLE trans_{0} DROP INDEX {0}_{1}_fulltext"


def conditional_sum(value=1, **cond):
    """Wrapper to generate SUM on boolean/enum values."""
    return Sum(Case(When(then=value, **cond), default=0, output_field=IntegerField()))


def using_postgresql():
    return connection.vendor == "postgresql"


def adjust_similarity_threshold(value: float):
    """
    Adjusts pg_trgm.similarity_threshold for the % operator.

    Ideally we would use directly similarity() in the search, but that doesn't seem
    to use index, while using % does.
    """
    if not using_postgresql():
        return
    with connection.cursor() as cursor:
        # The SELECT has to be executed first as othervise the trgm extension
        # might not yet be loaded and GUC setting not possible.
        if not hasattr(connection, "weblate_similarity"):
            cursor.execute("SELECT show_limit()")
            connection.weblate_similarity = cursor.fetchone()[0]
        # Change setting only for reasonably big difference
        if abs(connection.weblate_similarity - value) > 0.01:
            cursor.execute("SELECT set_limit(%s)", [value])
            connection.weblate_similarity = value


class PostgreSQLSearchLookup(PatternLookup):
    lookup_name = "search"
    param_pattern = "%s"

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return f"{lhs} %% {rhs} = true", params


class MySQLSearchLookup(models.Lookup):
    lookup_name = "search"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return f"MATCH ({lhs}) AGAINST ({rhs} IN NATURAL LANGUAGE MODE)", params


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
        return f"{lhs} ILIKE {rhs}", params


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
