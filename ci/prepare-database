#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

. ci/lib.sh

set -e

cleanup_database

if [ "$CI_DATABASE" = "mysql" ] || [ "$CI_DATABASE" = 'mariadb' ]; then
    # shellcheck disable=SC2046
    mysql $(get_mysql_args) -e 'SHOW VARIABLES LIKE "%version%";'
fi
if [ "$CI_DATABASE" = "postgresql" ]; then
    if [ -n "$CI_DB_PASSWORD" ]; then
        export PGPASSWORD="$CI_DB_PASSWORD"
    fi
    if [ -n "$CI_DB_PORT" ]; then
        export PGPORT="$CI_DB_PORT"
    fi
    psql --host="$CI_DB_HOST" -c 'SELECT version();' -U postgres
fi
