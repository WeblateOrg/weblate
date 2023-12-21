#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Testsuite executor

. ci/lib.sh

run_coverage ./manage.py compilemessages
check

run_coverage ./manage.py collectstatic --noinput --verbosity 0
check

run_coverage ./manage.py migrate --noinput --traceback
check

run_coverage ./manage.py check
check

run_coverage ./manage.py test
check
