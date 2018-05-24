#!/usr/bin/env bash

if [ ! -f ./weblate/settings.py ]
then
    cp ./weblate/settings_example.py ./weblate/settings.py
fi

export COMPOSE_FILE=docker-compose.dev.yml

docker-compose build

docker-compose up -d
docker-compose logs -f
