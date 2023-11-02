# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Database specific code to extend Django."""

from django.db import connection, models
from django.db.models import Case, IntegerField, Sum, When
from django.db.models.lookups import Contains, Exact, PatternLookup, Regex

from .inv_regex import invert_re

ESCAPED = frozenset(".\\+*?[^]$(){}=!<>|:-")

PG_TRGM = "CREATE INDEX {0}_{1}_fulltext ON trans_{0} USING GIN ({1} gin_trgm_ops {2})"
PG_DROP = "DROP INDEX {0}_{1}_fulltext"

MY_FTX = "CREATE FULLTEXT INDEX {0}_{1}_fulltext ON trans_{0}({1})"
MY_DROP = "ALTER TABLE trans_{0} DROP INDEX {0}_{1}_fulltext"


def conditional_sum(value=1, **cond):
    """Wrapper to generate SUM on boolean/enum values."""
    return Sum(Case(When(then=value, **cond), default=0, output_field=IntegerField()))


def using_postgresql():
    return connection.vendor == "postgresql"


class TransactionsTestMixin:
    @classmethod
    def _databases_support_transactions(cls):
        # This is workaround for MySQL as FULL TEXT index does not work
        # well inside a transaction, so we avoid using transactions for
        # tests. Otherwise we end up with no matches for the query.
        # See https://dev.mysql.com/doc/refman/5.6/en/innodb-fulltext-index.html
        if not using_postgresql():
            return False
        return super()._databases_support_transactions()


def adjust_similarity_threshold(value: float):
    """
    Adjusts pg_trgm.similarity_threshold for the % operator.

    Ideally we would use directly similarity() in the search, but that doesn't seem
    to use index, while using % does.
    """
    if not using_postgresql():
        return
    current_similarity = getattr(connection, "weblate_similarity", -1)
    # Ignore small differences
    if abs(current_similarity - value) < 0.05:
        return

    with connection.cursor() as cursor:
        # The SELECT has to be executed first as othervise the trgm extension
        # might not yet be loaded and GUC setting not possible.
        if current_similarity == -1:
            cursor.execute("SELECT show_limit()")

        # Adjust threshold
        cursor.execute("SELECT set_limit(%s)", [value])
        connection.weblate_similarity = value


def count_alnum(string):
    return sum(map(str.isalnum, string))


class PostgreSQLFallbackLookup(PatternLookup):
    def __init__(self, lhs, rhs):
        self.orig_lhs = lhs
        self.orig_rhs = rhs
        super().__init__(lhs, rhs)

    def needs_fallback(self):
        return isinstance(self.orig_rhs, str) and count_alnum(self.orig_rhs) <= 3


class FallbackStringMixin:
    """Avoid using index for lhs by concatenating to a string."""

    def process_lhs(self, compiler, connection, lhs=None):
        lhs_sql, params = super().process_lhs(compiler, connection, lhs)
        return f"{lhs_sql} || ''", params


class PostgreSQLRegexFallbackLookup(FallbackStringMixin, Regex):
    pass


class PostgreContainsFallbackLookup(FallbackStringMixin, Contains):
    pass


class PostgreExactFallbackLookup(FallbackStringMixin, Exact):
    pass


class PostgreSQLRegexLookup(Regex):
    def __init__(self, lhs, rhs):
        self.orig_lhs = lhs
        self.orig_rhs = rhs
        super().__init__(lhs, rhs)

    def needs_fallback(self):
        if not isinstance(self.orig_rhs, str):
            return False
        return (
            min((count_alnum(match) for match in invert_re(self.orig_rhs)), default=0)
            < 3
        )

    def as_sql(self, compiler, connection):
        if self.needs_fallback():
            return PostgreSQLRegexFallbackLookup(self.orig_lhs, self.orig_rhs).as_sql(
                compiler, connection
            )
        return super().as_sql(compiler, connection)


class PostgreSQLSearchLookup(PostgreSQLFallbackLookup):
    lookup_name = "search"
    param_pattern = "%s"

    def as_sql(self, compiler, connection):
        if self.needs_fallback():
            return PostgreContainsFallbackLookup(self.orig_lhs, self.orig_rhs).as_sql(
                compiler, connection
            )
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return f"{lhs} %% {rhs} = true", params


class MySQLSearchLookup(models.Lookup):
    lookup_name = "search"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return f"MATCH ({lhs}) AGAINST ({rhs} IN NATURAL LANGUAGE MODE)", params


class PostgreSQLSubstringLookup(PostgreSQLFallbackLookup):
    """
    Case insensitive substring lookup.

    This is essentially same as icontains in Django, but utilizes ILIKE
    operator which can use pg_trgm index.
    """

    lookup_name = "substring"

    def as_sql(self, compiler, connection):
        if self.needs_fallback():
            return PostgreContainsFallbackLookup(self.orig_lhs, self.orig_rhs).as_sql(
                compiler, connection
            )
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return f"{lhs} ILIKE {rhs}", params


def re_escape(pattern):
    """
    Escape for use in database regexp match.

    This is based on re.escape, but that one escapes too much.
    """
    string = list(pattern)
    for i, char in enumerate(pattern):
        if char == "\000":
            string[i] = "\\000"
        elif char in ESCAPED:
            string[i] = "\\" + char
    return "".join(string)
