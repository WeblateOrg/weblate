# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.core.checks import Warning, register

from weblate.utils.checks import weblate_check


def check_formats(app_configs, **kwargs):
    from weblate.formats.models import FILE_FORMATS

    message = "Failure in loading handler for {} file format: {}"
    return [
        weblate_check(
            f"weblate.W025.{key}", message.format(key, value.strip()), Warning
        )
        for key, value in FILE_FORMATS.errors.items()
    ]


class FormatsConfig(AppConfig):
    name = "weblate.formats"
    label = "formats"
    verbose_name = "Formats"

    def ready(self):
        super().ready()
        register(check_formats)
