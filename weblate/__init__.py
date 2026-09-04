# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.utils.urls import use_language_independent_url_resolver

# URLResolver selects its cache key before importing ROOT_URLCONF, so install
# the override as soon as the Weblate package is imported.
# ruff: ignore[non-empty-init-module]
use_language_independent_url_resolver()
