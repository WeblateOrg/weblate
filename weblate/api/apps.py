# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured

from weblate.api.ratelimits import get_rate_policies
from weblate.utils.checks import weblate_check

if TYPE_CHECKING:
    from django.core.checks import CheckMessage


@register()
def check_api_ratelimits(**kwargs: object) -> list[CheckMessage]:
    try:
        get_rate_policies()
    except ImproperlyConfigured as error:
        return [weblate_check("weblate.E050", str(error), Error)]
    return []


class ApiConfig(AppConfig):
    name = "weblate.api"
    label = "api"
    verbose_name = "API"
