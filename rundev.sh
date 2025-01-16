#!/usr/bin/env bash

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

GREEN='\033[0;32m'
NC='\033[0m'

# Used by docker-compose-plugin
WEBLATE_PORT=8080
export WEBLATE_PORT
WEBLATE_HOST=localhost:$WEBLATE_PORT
export WEBLATE_HOST
# Used by docker on start
USER_ID=$(id -u)
export USER_ID
GROUP_ID=$(id -g)
export GROUP_ID

cd dev-docker/

build() {
    mkdir -p data
    # Build the container
    docker compose build --build-arg USER_ID="$USER_ID" --build-arg GROUP_ID="$GROUP_ID"
    cat > .env << EOT
USER_ID="$USER_ID"
GROUP_ID="$GROUP_ID"
WEBLATE_PORT="$WEBLATE_PORT"
WEBLATE_HOST="$WEBLATE_HOST"
EOT
}

case $1 in
stop)
    docker compose down
    ;;
logs)
    shift
    docker compose logs "$@"
    ;;
compilemessages)
    shift
    docker compose exec -T -e WEBLATE_ADD_APPS=weblate.billing,weblate.legal weblate weblate compilemessages
    ;;
test)
    shift
    docker compose exec -T \
        --env CI_BASE_DIR=/tmp \
        --env CI_DATABASE=postgresql \
        --env CI_DB_HOST=database \
        --env CI_DB_NAME=weblate \
        --env CI_DB_USER=weblate \
        --env CI_DB_PASSWORD=weblate \
        --env DJANGO_SETTINGS_MODULE=weblate.settings_test \
        weblate weblate collectstatic --noinput
    docker compose exec -T \
        --env CI_BASE_DIR=/tmp \
        --env CI_DATABASE=postgresql \
        --env CI_DB_HOST=database \
        --env CI_DB_NAME=weblate \
        --env CI_DB_USER=weblate \
        --env CI_DB_PASSWORD=weblate \
        --env DJANGO_SETTINGS_MODULE=weblate.settings_test \
        --workdir /app/src \
        weblate pytest "$@"
    ;;
check)
    shift
    docker compose exec -T weblate weblate check "$@"
    ;;
build)
    build
    ;;
wait)
    TIMEOUT=0
    while ! docker compose ps | grep healthy; do
        echo "Waiting for the container startup..."
        sleep 5
        docker compose ps
        TIMEOUT=$((TIMEOUT + 1))
        if [ $TIMEOUT -gt 120 ]; then
            docker compose logs
            exit 1
        fi
    done
    ;;
start | restart | "")
    build

    # Start it up
    docker compose up -d --force-recreate
    echo -e "\n${GREEN}Running development version of Weblate on http://${WEBLATE_HOST}/${NC}\n"
    ;;
*)
    docker compose "$@"
    ;;
esac
