#!/usr/bin/env bash

if [ ! -f ./weblate/settings.py ]
then
    cp ./weblate/settings_example.py ./weblate/settings.py
fi

docker-compose up -d
docker-compose logs -f
