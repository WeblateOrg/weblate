# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.core.management.base import CommandError

from weblate.machinery.models import (
    MachineryInstallation,
    validate_service_configuration,
)
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(BaseCommand):
    help = "installs site-wide automatic suggestion service"

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument("--service", required=True, help="Service name")
        parser.add_argument("--slug", help="Optional installation slug")
        parser.add_argument("--id", type=int, help="Installation ID to update")
        parser.add_argument(
            "--configuration", default="{}", help="Service configuration in JSON"
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing service configuration",
        )

    def handle(self, *args, **options) -> None:
        if options["id"] is not None and not options["update"]:
            msg = "--id requires --update"
            raise CommandError(msg)
        if options["id"] is not None and options["slug"] is not None:
            msg = "Use --id or --slug to select an installation"
            raise CommandError(msg)
        service, configuration, errors = validate_service_configuration(
            options["service"], options["configuration"]
        )

        if service is None or errors:
            for error in errors:
                self.stderr.write(error)
            msg = "Invalid add-on configuration!"
            raise CommandError(msg)

        installations = MachineryInstallation.objects.filter(
            engine=options["service"],
            workspace__isnull=True,
            project__isnull=True,
        )
        if options["id"] is not None:
            installations = installations.filter(pk=options["id"])
        elif options["slug"] is not None:
            installations = installations.filter(slug=options["slug"])
        if options["update"]:
            try:
                installation = installations.get()
            except MachineryInstallation.DoesNotExist as error:
                if options["id"] is not None:
                    msg = "Select an existing site installation to update"
                    raise CommandError(msg) from error
                installation = MachineryInstallation(
                    engine=options["service"], slug=options["slug"] or ""
                )
            except MachineryInstallation.MultipleObjectsReturned as error:
                msg = "Select exactly one site installation to update"
                raise CommandError(msg) from error
        elif installations.exists():
            self.stdout.write(f"Service installed: {service.name}")
            return
        else:
            installation = MachineryInstallation(
                engine=options["service"], slug=options["slug"] or ""
            )
        installation.configuration = configuration
        try:
            installation.save()
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error
        self.stdout.write(f"Service installed: {service.name}")
