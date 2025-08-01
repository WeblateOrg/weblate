#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

# Filter out known issues in mypy checker
#
# - things which currently cannot be properly typed Django
# - testsuite mocks or simplifications (those probably should be addressed, but are too noisy now)

grep -vE '"Field" has no attribute "(choices|queryset|name)"|/test.* has incompatible type "MockUnit"; expected "Unit"|/test.*has incompatible type "None"; expected "Unit"'
