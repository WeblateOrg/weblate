# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Database specific code to extend Django."""

from __future__ import annotations

import time

from django.db import ProgrammingError, connections, models, transaction
from django.db.models.lookups import PatternLookup, Regex

from .inv_regex import invert_re

ESCAPED = frozenset(".\\+*?[^]$(){}=!<>|:-")

PG_TRGM = "CREATE INDEX {0}_{1}_fulltext ON trans_{0} USING GIN ({1} gin_trgm_ops {2})"
PG_DROP = "DROP INDEX {0}_{1}_fulltext"

MY_FTX = "CREATE FULLTEXT INDEX {0}_{1}_fulltext ON trans_{0}({1})"
MY_DROP = "ALTER TABLE trans_{0} DROP INDEX {0}_{1}_fulltext"


class MissingTransactionError(ProgrammingError):
    pass


def using_postgresql():
    return connections["default"].vendor == "postgresql"


class TransactionsTestMixin:
    @classmethod
    def _databases_support_transactions(cls):
        # This is workaround for MySQL as FULL TEXT index does not work
        # well inside a transaction, so we avoid using transactions for
        # tests. Otherwise we end up with no matches for the query.
        # See https://dev.mysql.com/doc/refman/5.6/en/innodb-fulltext-index.html
        if not using_postgresql():
            return False
        return super()._databases_support_transactions()  # type: ignore[misc]


def adjust_similarity_threshold(value: float) -> None:
    """
    Adjust pg_trgm.similarity_threshold for the % operator.

    Ideally we would use directly similarity() in the search, but that doesn't seem
    to use index, while using % does.
    """
    if not using_postgresql():
        return

    if "memory_db" in connections:
        connection = connections["memory_db"]
    else:
        connection = connections["default"]

    current_similarity = getattr(connection, "weblate_similarity", -1)
    # Ignore small differences
    if abs(current_similarity - value) < 0.05:
        return

    with connection.cursor() as cursor:
        # The SELECT has to be executed first as otherwise the trgm extension
        # might not yet be loaded and GUC setting not possible.
        if current_similarity == -1:
            cursor.execute("SELECT show_limit()")

        # Adjust threshold
        cursor.execute("SELECT set_limit(%s)", [value])
        connection.weblate_similarity = value  # type: ignore[attr-defined]


def count_alnum(string):
    return sum(map(str.isalnum, string))


class PostgreSQLFallbackLookupMixin:
    """
    Mixin to block PostgreSQL from using trigram index.

    It is ineffective for very short strings as these produce a lot of matches
    which need to be rechecked and full table scan is more effective in that
    case.

    It is performed by concatenating empty string which will prevent index usage.
    """

    def process_lhs(self, compiler, connection, lhs=None):
        if self._needs_fallback:  # type: ignore[attr-defined]
            lhs_sql, params = super().process_lhs(compiler, connection, lhs)  # type: ignore[misc]
            return f"{lhs_sql} || ''", params
        return super().process_lhs(compiler, connection, lhs)  # type: ignore[misc]


class PostgreSQLFallbackLookup(PostgreSQLFallbackLookupMixin, PatternLookup):
    def __init__(self, lhs, rhs) -> None:
        self._needs_fallback = isinstance(rhs, str) and count_alnum(rhs) <= 3
        super().__init__(lhs, rhs)


class PostgreSQLRegexLookup(PostgreSQLFallbackLookupMixin, Regex):
    def __init__(self, lhs, rhs) -> None:
        self._needs_fallback = isinstance(rhs, str) and (
            min((count_alnum(match) for match in invert_re(rhs)), default=0) < 3
        )
        super().__init__(lhs, rhs)


class PostgreSQLSearchLookup(PostgreSQLFallbackLookup):
    lookup_name = "search"

    def process_rhs(self, qn, connection):
        if not self._needs_fallback:
            self.param_pattern = "%s"
        return super().process_rhs(qn, connection)

    def get_rhs_op(self, connection, rhs):
        if self._needs_fallback:
            return connection.operators["contains"] % rhs
        return f"%% {rhs} = true"


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

    def get_rhs_op(self, connection, rhs):
        if self._needs_fallback:
            return connection.operators["contains"] % rhs
        return f"ILIKE {rhs}"


def re_escape(pattern: str) -> str:
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


def measure_database_latency() -> float:
    from weblate.trans.models import Project

    start = time.monotonic()
    Project.objects.exists()
    return round(1000 * (time.monotonic() - start))


def verify_in_transaction() -> None:
    """Verify the code is executed inside a transaction."""
    connection = transaction.get_connection()
    if not connection.in_atomic_block:
        raise MissingTransactionError
