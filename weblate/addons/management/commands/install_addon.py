#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import json

from django.core.management.base import CommandError

from weblate.addons.models import ADDONS, Addon
from weblate.auth.models import User, get_anonymous
from weblate.trans.management.commands import WeblateComponentCommand


class Command(WeblateComponentCommand):
    help = "installs addon to all listed components"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--addon", required=True, help="Addon name")
        parser.add_argument(
            "--configuration", default="{}", help="Addon configuration in JSON"
        )
        parser.add_argument(
            "--update", action="store_true", help="Update existing addons configuration"
        )

    def validate_form(self, form):
        if not form.is_valid():
            for error in form.non_field_errors():
                self.stderr.write(error)
            for field in form:
                for error in field.errors:
                    self.stderr.write(f"Error in {field.name}: {error}")
            raise CommandError("Invalid addon configuration!")

    def handle(self, *args, **options):
        try:
            addon_class = ADDONS[options["addon"]]
        except KeyError:
            raise CommandError("Addon not found: {}".format(options["addon"]))
        addon = addon_class()
        try:
            configuration = json.loads(options["configuration"])
        except ValueError as error:
            raise CommandError(f"Invalid addon configuration: {error}")
        try:
            user = User.objects.filter(is_superuser=True)[0]
        except IndexError:
            user = get_anonymous()
        for component in self.get_components(*args, **options):
            if addon.has_settings:
                form = addon.get_add_form(None, component, data=configuration)
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

            addon.create(component, configuration=configuration)
            self.stdout.write(f"Successfully installed on {component}")
