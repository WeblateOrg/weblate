# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.backends.postgresql.schema import (
    DatabaseSchemaEditor as OrigDatabaseSchemaEditorg,
)


class DatabaseSchemaEditor(OrigDatabaseSchemaEditorg):
    sql_create_table = OrigDatabaseSchemaEditorg.sql_create_table.replace(
        "CREATE TABLE ",
        "CREATE UNLOGGED TABLE ",
    )
