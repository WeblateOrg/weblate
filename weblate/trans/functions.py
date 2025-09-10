# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations
from typing import Any
from django.db.models import DateTimeField, Expression, Func
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models.sql.compiler import SQLCompiler, _AsSqlType

VALID_UNIT_VALUES = {
    "MICROSECOND",
    "SECOND",
    "MINUTE",
    "HOUR",
    "DAY",
    "WEEK",
    "MONTH",
    "QUARTER",
    "YEAR",
}


class MySQLTimestampAdd(Func):
    function = "TIMESTAMPADD"
    output_field = DateTimeField()

    def __init__(self, unit: str, interval: Expression, timestamp: Expression):
        # unit is a string (not a Value/Expression) as mysql/mariadb throws an
        # error if the unit argument to TIMESTAMPADD is quoted.
        if unit not in VALID_UNIT_VALUES:
            msg = f"Invalid unit: {unit}"
            raise ValueError(msg)
        self.unit = unit
        super().__init__(interval, timestamp)

    def as_sql(
        self,
        compiler: SQLCompiler,
        connection: BaseDatabaseWrapper,
        function: str | None = None,
        template: str | None = None,
        arg_joiner: str | None = None,
        **extra_context: Any,
    ) -> _AsSqlType:
        interval_sql, interval_params = self.source_expressions[0].as_sql(compiler, connection)
        timestamp_sql, timestamp_params = self.source_expressions[1].as_sql(compiler, connection)

        # override default template to avoid addition of unnecessary parentheses
        # around function arguments
        sql = f"{self.function}({self.unit}, {interval_sql}, {timestamp_sql})"
        params = interval_params + timestamp_params  # type: ignore[operator]
        return sql, params
