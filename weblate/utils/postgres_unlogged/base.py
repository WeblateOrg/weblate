# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.backends.postgresql.base import *  # noqa: F403
from django.db.backends.postgresql.base import DatabaseWrapper as OrigDatabaseWrapper

from .schema import DatabaseSchemaEditor


class DatabaseWrapper(OrigDatabaseWrapper):  # type: ignore [no-redef]
    SchemaEditorClass = DatabaseSchemaEditor
