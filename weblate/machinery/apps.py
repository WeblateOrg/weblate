# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.core.checks import Warning, register

from weblate.utils.checks import weblate_check


@register
def check_machinery(app_configs, **kwargs):
    from weblate.machinery.models import MACHINERY

    # Needed to load the data
    MACHINERY.data  # noqa: B018
    return [
        weblate_check(
            f"weblate.W039.{key.split('.')[-1]}",
            str(value),
            Warning,
        )
        for key, value in MACHINERY.errors.items()
    ]


class VCSConfig(AppConfig):
    name = "weblate.machinery"
    label = "machinery"
    verbose_name = "Machinery"
