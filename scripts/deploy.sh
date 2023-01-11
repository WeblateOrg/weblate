#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Very simple script to deploy from git
git pull --rebase
./manage.py migrate
./manage.py compilemessages
./manage.py collectstatic --noinput
./manage.py setuplang
