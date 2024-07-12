# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json

from django.core.management.base import CommandError

from weblate.configuration.models import Setting
from weblate.machinery.models import MACHINERY
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

    def validate_form(self, form) -> None:
        if not form.is_valid():
            for error in form.non_field_errors():
                self.stderr.write(error)
            for field in form:
                for error in field.errors:
                    self.stderr.write(f"Error in {field.name}: {error}")
            raise CommandError("Invalid add-on configuration!")

    def handle(self, *args, **options) -> None:
        try:
            service = MACHINERY[options["service"]]
        except KeyError as error:
            raise CommandError(
                "Service not found: {}".format(options["service"])
            ) from error
        try:
            configuration = json.loads(options["configuration"])
        except ValueError as error:
            raise CommandError(f"Invalid service configuration: {error}") from error
        if service.settings_form is not None:
            form = service.settings_form(service, data=configuration)
            self.validate_form(form)

        setting, created = Setting.objects.get_or_create(
            category=Setting.CATEGORY_MT,
            name=options["service"],
            defaults={"value": configuration},
        )
        if not created and options["update"]:
            setting.value = configuration
            setting.save()
        self.stdout.write(f"Service installed: {service.name}")
