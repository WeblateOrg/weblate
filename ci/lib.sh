# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# shell library to help executing tests

# shellcheck shell=sh

if [ -z "$TERM" ]; then
    export TERM=xterm-256color
fi

check() {
    RET=$?
    if [ $RET -ne 0 ]; then
        exit $RET
    fi
}

run_coverage() {
    uv run --no-sources --all-extras coverage run --source . --append "$@"
}

get_mysql_args() {
    # shellcheck disable=SC2153
    args="--host=$CI_DB_HOST --user=root"
    if [ -n "$CI_DB_PORT" ]; then
        args="$args --port=$CI_DB_PORT"
    fi
    echo "$args"
}

cleanup_database() {
    rm -f weblate.db

    if [ "$CI_DATABASE" = "mysql" ] || [ "$CI_DATABASE" = 'mariadb' ]; then
        if [ -n "$CI_DB_PASSWORD" ]; then
            export MYSQL_PWD="$CI_DB_PASSWORD"
        fi
        # shellcheck disable=SC2046
        mysql $(get_mysql_args) -e 'SET GLOBAL character_set_server=utf8mb4'
        # shellcheck disable=SC2046
        mysql $(get_mysql_args) -e 'SET GLOBAL collation_server=utf8mb4_general_ci'
        # shellcheck disable=SC2046
        mysql $(get_mysql_args) -e 'DROP DATABASE IF EXISTS weblate;'
        # shellcheck disable=SC2046
        mysql $(get_mysql_args) -e 'CREATE DATABASE weblate CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;'
    fi

    if [ "$CI_DATABASE" = "postgresql" ]; then
        if [ -n "$CI_DB_PASSWORD" ]; then
            export PGPASSWORD="$CI_DB_PASSWORD"
        fi
        if [ -n "$CI_DB_PORT" ]; then
            export PGPORT="$CI_DB_PORT"
        fi
        psql --host="$CI_DB_HOST" -c 'DROP DATABASE IF EXISTS weblate;' -U postgres
        psql --host="$CI_DB_HOST" -c 'CREATE DATABASE weblate;' -U postgres
        # Replaces weblate/utils/migrations/0001_alter_role.py
        psql --host="$CI_DB_HOST" -c 'ALTER ROLE postgres SET timezone = UTC;' -U postgres
    fi
}

print_step() {
    tput setaf 2
    echo "$@"
    tput sgr0
}

print_version() {
    for cmd in "$@"; do
        if command -v "$cmd"; then
            $cmd --version
            return
        fi
    done
    echo "not found..."
}
