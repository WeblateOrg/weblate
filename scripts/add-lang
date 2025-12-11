#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

./manage.py makemessages --keep-pot -l "$1" -i 'repos/*' -i 'docs/*' -i 'examples/*'
./manage.py makemessages --keep-pot -l "$1" -i 'repos/*' -i 'docs/*' -i 'examples/*' -d djangojs
git add "weblate/locale/$1/"
git commit -m "Added $1 language"
