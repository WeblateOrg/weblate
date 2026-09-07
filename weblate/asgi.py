# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ASGI config for Weblate."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

from weblate.utils.startup import preload_url_patterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")

application = get_asgi_application()
preload_url_patterns()
