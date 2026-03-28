# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Minimal Django settings for extraction-only management commands."""

import os

from django.core.management.utils import get_random_secret_key

SECRET_KEY = get_random_secret_key()
USE_I18N = True
LOGGING_CONFIG = None
LOCALE_FILTER_FILES = False
INSTALLED_APPS: list[str] = []
LOCALE_PATHS = [os.environ["WEBLATE_EXTRACT_LOCALE_PATH"]]
