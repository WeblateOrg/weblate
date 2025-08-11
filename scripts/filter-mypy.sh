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
# - testsuite mocks or simplifications (those probably should be addressed, but are too noisy now)

grep -vE '"Field" has no attribute "(choices|queryset|name|valid)"|"Task.*" has no attribute "delay_on_commit"|.Settings. object has no attribute|/test.* has incompatible type "Mock[A-Za-z]*; expected "(Unit|Check)"|/test.*has incompatible type "None"; expected "Unit"'
