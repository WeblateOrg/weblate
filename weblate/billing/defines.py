# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta

LIBRE_PROBLEM_PERIOD = timedelta(days=90)
LIBRE_WARNING_PERIOD = timedelta(days=30)
LIBRE_CLEANUP_TRIAL_PERIOD = timedelta(days=30)

TRIAL_DAYS: int = 14
TRIAL_PLAN_SLUG: str = "640k"
REMOVAL_EXTENSION_DAYS: int = 14
