# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.management.base import CommandError

from weblate.configuration.models import Setting, SettingCategory
from weblate.machinery.models import validate_service_configuration
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "installs site-wide automatic suggestion service"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument("--service", required=True, help="Service name")
        parser.add_argument(
            "--configuration", default="{}", help="Service configuration in JSON"
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing service configuration",
        )

    def handle(self, *args, **options) -> None:
        service, configuration, errors = validate_service_configuration(
            options["service"], options["configuration"]
        )

        if service is None or errors:
            for error in errors:
                self.stderr.write(error)
            msg = "Invalid add-on configuration!"
            raise CommandError(msg)

        setting, created = Setting.objects.get_or_create(
            category=SettingCategory.MT,
            name=options["service"],
            defaults={"value": configuration},
        )
        if not created and options["update"]:
            setting.value = configuration
            setting.save()
        self.stdout.write(f"Service installed: {service.name}")
