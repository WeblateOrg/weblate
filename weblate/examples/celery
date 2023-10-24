#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Simple wrapper to start/stop celery workers

# Set the app using environment instead of command-line as that got broken
# in the 4.4.7 release, see
# https://github.com/celery/celery/issues/6285
export CELERY_APP=weblate.utils

python -m celery multi "$1" \
    celery \
    "--pidfile=$PWD/weblate-%n.pid" \
    "--logfile=$PWD/weblate-%n%I.log" --loglevel=DEBUG \
    --queues:celery=celery,notify,memory,translate,backup \
    --beat:celery
