# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.api.metrics import METRICS_FORMATS, render_server_metrics
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(BaseCommand):
    help = "display server metrics"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--format",
            choices=METRICS_FORMATS,
            default="json",
            help="output format (default: json)",
        )

    def handle(self, *args, **options) -> None:
        self.stdout.write(render_server_metrics(options["format"]))
