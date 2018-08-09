#!/usr/bin/env bash

GREEN='\033[0;32m'
NC='\033[0m'

if [ ! -f ./weblate/settings.py ]
then
    cp ./weblate/settings_dev.py ./weblate/settings.py
fi

export USER_ID=$(id -u)
export GROUP_ID=$(id -g)
export WEBLATE_HOST=0.0.0.0:8080

export COMPOSE_FILE=docker-compose.dev.yml

docker-compose build

docker-compose up -d --force-recreate
echo -e "\n${GREEN}Running development version of Weblate on http://${WEBLATE_HOST}/${NC}\n"

docker-compose logs -f
