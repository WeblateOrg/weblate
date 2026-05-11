#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

# Filter out known issues in mypy checker
#
# - things which currently cannot be properly typed Django
# - https://github.com/sbdchd/celery-types/issues/157
# - settings do not have proper type annotations

grep -vE '"Field" has no attribute "(choices|queryset|name)"|.Settings. object has no attribute'
