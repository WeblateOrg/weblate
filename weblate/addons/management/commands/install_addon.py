# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json

from django.core.management.base import CommandError

from weblate.addons.models import ADDONS, Addon
from weblate.auth.models import User, get_anonymous
from weblate.trans.management.commands import WeblateComponentCommand


class Command(WeblateComponentCommand):
    help = "installs add-on to all listed components"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument("--addon", required=True, help="Add-on name")
        parser.add_argument(
            "--configuration", default="{}", help="Add-on configuration in JSON"
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing add-ons configuration",
        )

    def validate_form(self, form) -> None:
        if not form.is_valid():
            for error in form.non_field_errors():
                self.stderr.write(error)
            for field in form:
                for error in field.errors:
                    self.stderr.write(f"Error in {field.name}: {error}")
            msg = "Invalid add-on configuration!"
            raise CommandError(msg)

    def handle(self, *args, **options) -> None:
        try:
            addon = ADDONS[options["addon"]]
        except KeyError as error:
            msg = "Add-on not found: {}".format(options["addon"])
            raise CommandError(msg) from error
        try:
            configuration = json.loads(options["configuration"])
        except json.JSONDecodeError as error:
            msg = f"Invalid add-on configuration: {error}"
            raise CommandError(msg) from error
        try:
            user = User.objects.filter(is_superuser=True)[0]
        except IndexError:
            user = get_anonymous()
        for component in self.get_components(*args, **options):
            if addon.has_settings():
                form = addon.get_add_form(None, component=component, data=configuration)
                self.validate_form(form)
            addons = Addon.objects.filter_component(component).filter(name=addon.name)
            if addons:
                if options["update"]:
                    for addon_component in addons:
                        addon_component.addon.configure(configuration)
                    self.stdout.write(f"Successfully updated on {component}")
                else:
                    self.stderr.write(f"Already installed on {component}")
                continue

            if not addon.can_install(component, user):
                self.stderr.write(f"Can not install on {component}")
                continue

            addon.create(component=component, configuration=configuration)
            self.stdout.write(f"Successfully installed on {component}")
