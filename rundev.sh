#!/usr/bin/env bash

set -e

GREEN='\033[0;32m'
NC='\033[0m'

export USER_ID=$(id -u)
export GROUP_ID=$(id -g)
export WEBLATE_HOST=127.0.0.1:8080

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
        mkdir -p data/python/customize
        touch data/python/customize/__init__.py
        touch data/python/customize/models.py
        docker-compose build

        docker-compose up -d --force-recreate
        echo -e "\n${GREEN}Running development version of Weblate on http://${WEBLATE_HOST}/${NC}\n"

        docker-compose logs -f
        ;;
    *)
        docker-compose "$@"
        ;;
esac
