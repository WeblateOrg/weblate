#!/usr/bin/env bash

if [ ! -f ./weblate/settings.py ]
then
    cp ./weblate/settings_dev.py ./weblate/settings.py
fi

export USER_ID=$(id -u)
export GROUP_ID=$(id -g)

export COMPOSE_FILE=docker-compose.dev.yml

docker-compose build

docker-compose up -d --force-recreate
docker-compose logs -f
