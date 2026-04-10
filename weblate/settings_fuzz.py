# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
# pylint: disable=unused-wildcard-import,wildcard-import

from __future__ import annotations

from weblate.settings_test import *  # noqa: F403

for app in (
    "django.contrib.admin",
    "django_otp_webauthn",
    "weblate.billing",
    "weblate.fonts",
    "weblate.legal",
):
    if app in INSTALLED_APPS:
        INSTALLED_APPS.remove(app)

CHECK_LIST = None
ROOT_URLCONF = "fuzzing.urls"
