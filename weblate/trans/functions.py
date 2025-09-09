# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.models import DateTimeField, Func

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

    def __init__(self, unit, interval, timestamp):
        if unit not in VALID_UNIT_VALUES:
            msg = f"Invalid unit: {unit}"
            raise ValueError(msg)
        self.unit = unit
        super().__init__(interval, timestamp)

    def as_sql(
        self,
        compiler,
        connection,
        **kwargs,
    ):
        interval_sql, interval_params = self.source_expressions[0].as_sql(
            compiler, connection
        )
        timestamp_sql, timestamp_params = self.source_expressions[1].as_sql(
            compiler, connection
        )

        sql = f"{self.function}({self.unit}, {interval_sql}, {timestamp_sql})"
        params = interval_params + timestamp_params
        return sql, params
