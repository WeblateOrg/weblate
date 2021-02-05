#!/usr/bin/env bash

set -e

GREEN='\033[0;32m'
NC='\033[0m'

# Used by docker-compose
WEBLATE_HOST=127.0.0.1:8080
export WEBLATE_HOST
# Used by docker on start
USER_ID=$(id -u)
export USER_ID
GROUP_ID=$(id -g)
export GROUP_ID


cd dev-docker/

case $1 in
    stop)
        docker-compose down
        ;;
    logs)
        shift
        docker-compose logs "$@"
        ;;
    test)
        shift
        docker-compose exec -e WEBLATE_DATA_DIR=/tmp/test-data -e WEBLATE_CELERY_EAGER=1 weblate weblate test --noinput "$@"
        ;;
    start|restart|"")
        # Build single requirements file
        sed '/^-r/D' ../requirements.txt ../requirements-optional.txt ../requirements-test.txt > weblate-dev/requirements.txt
        # Build the container
        docker-compose build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g)

        # Start it up
        docker-compose up -d --force-recreate
        echo -e "\n${GREEN}Running development version of Weblate on http://${WEBLATE_HOST}/${NC}\n"
        ;;
    *)
        docker-compose "$@"
        ;;
esac
