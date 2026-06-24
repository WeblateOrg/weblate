# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.management.base import CommandError

from weblate.utils.management.base import BaseCommand
from weblate.utils.tasks import run_database_backup, run_settings_backup
from weblate.wladmin.models import BackupService
from weblate.wladmin.tasks import run_backup_service

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.core.management.base import CommandParser

    from weblate.wladmin.models import BackupLog


class Command(BaseCommand):
    help = "runs configured backups"

    def add_arguments(self, parser: CommandParser) -> None:
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--service",
            type=int,
            help="run backup for a configured backup service ID",
        )
        group.add_argument(
            "--all",
            action="store_true",
            help="run backup for all enabled backup services",
        )
        group.add_argument(
            "--list",
            action="store_true",
            dest="list_services",
            help="list configured backup service IDs",
        )

    def write_service_logs(
        self, service: BackupService, logs: Sequence[BackupLog], *, error: bool
    ) -> None:
        if not logs:
            return

        output = self.stderr if error else self.stdout
        output.write(f"Backup service {service.pk}: {service.repository}")
        for log in logs:
            output.write(f"{log.get_event_display()}:")
            output.write(log.log.rstrip())

    def run_service(self, service: BackupService, *, verbose: bool) -> bool:
        last_log_pk = (
            service.backuplog_set.order_by("-pk").values_list("pk", flat=True).first()
            or 0
        )
        success = run_backup_service(service)
        logs = list(service.backuplog_set.filter(pk__gt=last_log_pk).order_by("pk"))
        has_errors = any(log.event == "error" for log in logs)

        if verbose:
            self.write_service_logs(service, logs, error=False)
        elif not success or has_errors:
            self.write_service_logs(service, logs, error=True)
        return success and not has_errors

    def handle(self, *args, **options) -> None:
        if options["list_services"]:
            for service in BackupService.objects.order_by("pk"):
                status = "enabled" if service.enabled else "disabled"
                self.stdout.write(f"{service.pk}\t{status}\t{service.repository}")
            return

        if options["service"] is not None:
            try:
                services = [BackupService.objects.get(pk=options["service"])]
            except BackupService.DoesNotExist as error:
                msg = f"Backup service {options['service']} does not exist"
                raise CommandError(msg) from error
        else:
            services = list(BackupService.objects.filter(enabled=True).order_by("pk"))

        run_settings_backup()
        run_database_backup()
        verbose = int(options["verbosity"]) > 1
        failed_services = [
            service.pk
            for service in services
            if not self.run_service(service, verbose=verbose)
        ]
        if failed_services:
            failed = ", ".join(str(pk) for pk in failed_services)
            msg = f"Backup service failed: {failed}"
            raise CommandError(msg)
