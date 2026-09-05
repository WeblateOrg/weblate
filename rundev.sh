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

ROOT=$(cd "$(dirname "$0")" && pwd)

test_environment() {
    "$ROOT/scripts/devcontainer" --backend compose "$@"
}

# Tests do not need the application environment or its host-port configuration.
if [ "${1:-}" = test ]; then
    shift
    test_environment up
    test_environment exec -- uv run --no-sync pytest -n auto "$@"
    exit $?
fi

cd "$ROOT/dev-docker/"

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

case ${1:-} in
stop)
    status=0
    docker compose down || status=$?
    if [ -f "$ROOT/.devcontainer/compose.local.json" ]; then
        test_environment stop || status=$?
    fi
    exit "$status"
    ;;
logs)
    shift
    status=0
    docker compose logs "$@" || status=$?
    if [ "$#" -eq 0 ] && [ -f "$ROOT/.devcontainer/compose.local.json" ]; then
        test_environment logs || status=$?
    fi
    exit "$status"
    ;;
compilemessages)
    shift
    docker compose exec -T -e WEBLATE_ADD_APPS=weblate.billing,weblate.legal weblate weblate compilemessages
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
    while ! docker compose ps | grep "weblate-dev:.*healthy"; do
        echo "Waiting for the container startup..."
        sleep 5
        docker compose ps
        TIMEOUT=$((TIMEOUT + 1))
        if [ $TIMEOUT -gt 60 ]; then
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
    echo "maildev is running on http://localhost:1080/"
    ;;
*)
    docker compose "$@"
    ;;
esac
