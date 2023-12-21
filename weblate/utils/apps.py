# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.core.checks import register
from django.db.models import CharField, TextField
from django.db.models.functions import MD5, Lower
from django.db.models.lookups import Regex

from weblate.utils.checks import (
    check_cache,
    check_celery,
    check_data_writable,
    check_database,
    check_diskspace,
    check_encoding,
    check_errors,
    check_mail_connection,
    check_perms,
    check_settings,
    check_site,
    check_version,
)
from weblate.utils.db import using_postgresql
from weblate.utils.errors import init_error_collection

from .db import (
    MySQLSearchLookup,
    PostgreSQLRegexLookup,
    PostgreSQLSearchLookup,
    PostgreSQLSubstringLookup,
)


class UtilsConfig(AppConfig):
    name = "weblate.utils"
    label = "utils"
    verbose_name = "Utils"

    def ready(self):
        super().ready()
        register(check_data_writable)
        register(check_mail_connection, deploy=True)
        register(check_celery, deploy=True)
        register(check_cache, deploy=True)
        register(check_settings, deploy=True)
        register(check_database, deploy=True)
        register(check_site)
        register(check_perms, deploy=True)
        register(check_errors, deploy=True)
        register(check_version, deploy=True)
        register(check_encoding)
        register(check_diskspace, deploy=True)

        init_error_collection()

        if using_postgresql():
            lookups = [
                (PostgreSQLSearchLookup,),
                (PostgreSQLSubstringLookup,),
                (PostgreSQLRegexLookup, "trgm_regex"),
            ]
        else:
            lookups = [
                (MySQLSearchLookup,),
                (MySQLSearchLookup, "substring"),
                (Regex, "trgm_regex"),
            ]

        lookups.append((MD5,))
        lookups.append((Lower,))

        for lookup in lookups:
            CharField.register_lookup(*lookup)
            TextField.register_lookup(*lookup)
