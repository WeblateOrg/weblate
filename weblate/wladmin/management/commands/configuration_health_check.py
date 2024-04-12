# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.utils.management.base import BaseCommand
from weblate.wladmin.models import ConfigurationError


class Command(BaseCommand):
    help = "runs a configuration health check"

    def handle(self, *args, **options) -> None:
        ConfigurationError.objects.configuration_health_check()
