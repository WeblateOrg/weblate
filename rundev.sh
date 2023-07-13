#!/usr/bin/env bash

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

GREEN='\033[0;32m'
NC='\033[0m'

# Used by docker-compose-plugin
WEBLATE_HOST=127.0.0.1:8080
export WEBLATE_HOST
# Used by docker on start
USER_ID=$(id -u)
export USER_ID
GROUP_ID=$(id -g)
export GROUP_ID


cd dev-docker/

build() {
    mkdir -p data
    # Build single requirements file
    sed '/^-r/D' ../requirements.txt ../requirements-optional.txt ../requirements-test.txt > weblate-dev/requirements.txt
    # Build the container
    docker compose build --build-arg USER_ID="$(id -u)" --build-arg GROUP_ID="$(id -g)"

    DOCKER_PYTHON="$(docker inspect weblate-dev:latest | jq -r '.[].Config.Env[]|select(match("^PYVERSION"))|.[index("=")+1:]')"
    echo "DOCKER_PYTHON=$DOCKER_PYTHON" > .env
}

case $1 in
    stop)
        docker compose down
        ;;
    logs)
        shift
        docker compose logs "$@"
        ;;
    test)
        shift
        docker compose exec -T -e WEBLATE_DATA_DIR=/tmp/test-data -e WEBLATE_CELERY_EAGER=1 -e WEBLATE_SITE_TITLE=Weblate -e WEBLATE_ADD_APPS=weblate.billing,weblate.legal weblate weblate test --noinput "$@"
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
        while ! docker compose ps | grep healthy ; do
            echo "Waiting for the container startup..."
            sleep 1
            docker compose ps
            TIMEOUT=$((TIMEOUT + 1))
            if [ $TIMEOUT -gt 120 ] ; then
              docker compose logs
              exit 1
            fi
        done
        ;;
    start|restart|"")
        build

        # Start it up
        docker compose up -d --force-recreate
        echo -e "\n${GREEN}Running development version of Weblate on http://${WEBLATE_HOST}/${NC}\n"
        ;;
    *)
        docker compose "$@"
        ;;
esac
