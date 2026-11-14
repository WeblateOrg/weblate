# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# SQL structure consists of internal fragments only; values use bound parameters.

"""
Bounded SQL aggregates for daily metrics.

Only target identities cross the Python/database boundary. In particular, category
membership and history deduplication stay in PostgreSQL, even for large trees.
SQL fragments below are internal constants; identities and dates are parameters.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from uuid import UUID

from django.db import connections

from weblate.trans.models.change import dt_as_day_range

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

Identity = int | UUID
BATCH_SIZE = 500


def membership(scope: str, *, linked: bool = False) -> str:
    """Return distinct (target, component) membership for a bounded target CTE."""
    if scope == "category":
        return """
            SELECT t.id AS target, c.id AS component_id
            FROM trans_category child
            LEFT JOIN trans_category parent ON parent.id = child.category_id
            JOIN targets t ON t.id IN (child.id, child.category_id, parent.category_id)
            JOIN trans_component c ON c.category_id = child.id
            UNION
            SELECT t.id, link.component_id
            FROM trans_category child
            LEFT JOIN trans_category parent ON parent.id = child.category_id
            JOIN targets t ON t.id IN (child.id, child.category_id, parent.category_id)
            JOIN trans_component_links link ON link.category_id = child.id
        """
    if scope == "component_list":
        return """SELECT t.id AS target, m.component_id
            FROM targets t JOIN trans_componentlist_components m
            ON m.componentlist_id = t.id"""
    if scope == "project":
        result = """SELECT t.id AS target, c.id AS component_id
            FROM targets t JOIN trans_component c ON c.project_id = t.id"""
        if linked:
            result += """ UNION SELECT t.id, link.component_id
                FROM targets t JOIN trans_component_links link ON link.project_id = t.id"""
        return result
    if scope == "workspace":
        return """SELECT t.id AS target, c.id AS component_id
            FROM targets t JOIN trans_project p ON p.workspace_id = t.id
            JOIN trans_component c ON c.project_id = p.id"""
    if scope == "component":
        return "SELECT id AS target, id AS component_id FROM targets"
    raise ValueError(scope)


def target_cte(ids: Sequence[Identity]) -> tuple[str, list]:
    return (
        "targets(id) AS (VALUES " + ", ".join(["(%s)"] * len(ids)) + ")",
        list(ids),
    )


def history(
    scope: str,
    ids: Sequence[Identity],
    date: dt.date,
    using: str,
    pairs: Sequence[tuple[int, int]] = (),
) -> dict:
    """Aggregate history in two queries, bounded by targets or parent/language pairs."""
    cte, parameters = target_cte(ids)
    if pairs:
        cte = (
            # ruff: ignore[hardcoded-sql-expression]
            "requested(id, language_id) AS (VALUES "
            + ", ".join(["(%s, %s)"] * len(pairs))
            + "), targets AS (SELECT DISTINCT id FROM requested)"
        )
        parameters = [value for pair in pairs for value in pair]
    fields = "c.id, c.user_id, c.timestamp, c.translation_id"
    if scope in {"category", "component_list"}:
        cte += f", members AS ({membership(scope)})"
        # ruff: ignore[hardcoded-sql-expression]
        source = f"SELECT m.target, {fields} FROM members m JOIN trans_change c ON c.component_id = m.component_id"
        if scope == "category":
            # ruff: ignore[hardcoded-sql-expression]
            source += f""" UNION ALL SELECT t.id, {fields}
                FROM targets t JOIN trans_change c ON c.category_id = t.id
                WHERE NOT EXISTS (SELECT 1 FROM members m
                    WHERE m.target = t.id AND m.component_id = c.component_id)"""
    else:
        # Scope names come exclusively from the collector's fixed dispatch table.
        column = {
            "project": "project_id",
            "workspace": "workspace_id",
            "component": "component_id",
            "translation": "translation_id",
            "language": "language_id",
        }[scope]
        # ruff: ignore[hardcoded-sql-expression]
        source = f"SELECT t.id AS target, {fields} FROM targets t JOIN trans_change c ON c.{column} = t.id"
    cte += f", history AS ({source})"
    group = "h.target"
    join = ""
    if pairs:
        group += ", tr.language_id"
        join = """JOIN trans_translation tr ON tr.id = h.translation_id
            JOIN requested r ON r.id = h.target AND r.language_id = tr.language_id"""
    start, end = dt_as_day_range(date - dt.timedelta(days=1))
    recent = dt_as_day_range(date - dt.timedelta(days=30))[0]
    result = {}
    with connections[using].cursor() as cursor:
        cursor.execute(
            # ruff: ignore[hardcoded-sql-expression]
            f"""WITH {cte} SELECT {group},
                COUNT(h.id) FILTER (WHERE h.timestamp BETWEEN %s AND %s),
                COUNT(DISTINCT h.user_id) FILTER (WHERE u.is_active AND NOT u.is_bot)
                FROM history h LEFT JOIN weblate_auth_user u ON u.id = h.user_id
                {join} WHERE h.timestamp >= %s GROUP BY {group}""",
            [*parameters, start, end, recent],
        )
        for row in cursor:
            key = (row[0], row[1]) if pairs else row[0]
            result[key] = {
                "changes": row[-2],
                "contributors": row[-1],
                "contributors_total": 0,
            }
        cursor.execute(
            # ruff: ignore[hardcoded-sql-expression]
            f"""WITH {cte} SELECT {group}, COUNT(DISTINCT h.user_id)
                FROM history h JOIN weblate_auth_user u ON u.id = h.user_id
                {join} WHERE u.is_active AND NOT u.is_bot GROUP BY {group}""",
            parameters,
        )
        for row in cursor:
            key = (row[0], row[1]) if pairs else row[0]
            result.setdefault(key, {"changes": 0, "contributors": 0})[
                "contributors_total"
            ] = row[-1]
    return result


def language_pairs(
    scope: str, ids: Sequence[Identity], using: str
) -> Iterator[tuple[int, int]]:
    """Stream existing pairs without fetching any component or translation objects."""
    cte, parameters = target_cte(ids)
    connection = connections[using]
    # A server-side cursor keeps even a large project's language pairs bounded.
    with connection.chunked_cursor() as cursor:
        cursor.execute(
            # ruff: ignore[hardcoded-sql-expression]
            f"""WITH {cte}, members AS ({membership(scope, linked=True)})
                SELECT DISTINCT m.target, tr.language_id FROM members m
                JOIN trans_translation tr ON tr.component_id = m.component_id
                ORDER BY m.target, tr.language_id""",
            parameters,
        )
        while rows := cursor.fetchmany(BATCH_SIZE):
            yield from rows


def counters(scope: str, ids: Sequence[Identity], using: str) -> dict:
    """Calculate auxiliary counts separately to avoid multiplying joined rows."""
    from weblate.accounts.models import Profile  # ruff: ignore[import-outside-top-level]
    from weblate.memory.models import MemoryScope  # ruff: ignore[import-outside-top-level]

    cte, parameters = target_cte(ids)
    queries = {}
    if scope in {"project", "workspace", "category", "component"}:
        cte += f", members AS ({membership(scope)})"
        if scope != "component":
            queries["components"] = (
                "SELECT target, COUNT(*) FROM members GROUP BY target"
            )
        queries["translations"] = """SELECT m.target, COUNT(*) FROM members m
            JOIN trans_translation tr ON tr.component_id = m.component_id GROUP BY m.target"""
        if scope != "category":
            queries["screenshots"] = """SELECT m.target, COUNT(*) FROM members m
                JOIN trans_translation tr ON tr.component_id = m.component_id
                JOIN screenshots_screenshot s ON s.translation_id = tr.id GROUP BY m.target"""
    if scope == "translation":
        queries["screenshots"] = """SELECT t.id, COUNT(*) FROM targets t
            JOIN screenshots_screenshot s ON s.translation_id = t.id GROUP BY t.id"""
    if scope == "language":
        table = connections[using].ops.quote_name(
            Profile.languages.through._meta.db_table  # ruff: ignore[private-member-access]
        )
        queries["users"] = (
            # ruff: ignore[hardcoded-sql-expression]
            f"SELECT t.id, COUNT(*) FROM targets t JOIN {table} p ON p.language_id = t.id GROUP BY t.id"
        )
    if scope == "workspace":
        queries["projects"] = """SELECT t.id, COUNT(*) FROM targets t
            JOIN trans_project p ON p.workspace_id = t.id GROUP BY t.id"""
    if scope in {"project", "workspace"}:
        scopes = (
            (MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE)
            if scope == "project"
            else (MemoryScope.SCOPE_WORKSPACE,)
        )
        # These are fixed integer model constants, never external SQL input.
        scope_sql = ", ".join(str(value) for value in scopes)
        # ruff: ignore[hardcoded-sql-expression]
        queries["memory"] = f"""SELECT t.id, COUNT(DISTINCT m.memory_id) FROM targets t
            JOIN memory_memoryscope m ON m.{scope}_id = t.id
            WHERE m.scope IN ({scope_sql}) GROUP BY t.id"""
    result: dict[Identity, dict[str, int]] = {pk: {} for pk in ids}
    with connections[using].cursor() as cursor:
        for name, query in queries.items():
            cursor.execute(f"WITH {cte} {query}", parameters)
            values = dict(cursor)
            for pk in ids:
                result[pk][name] = values.get(pk, 0)
    return result
