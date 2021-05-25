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

from textwrap import wrap

from weblate.addons.models import ADDONS, Addon
from weblate.trans.models import Component, Project
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "List installed add-ons"

    def handle(self, *args, **options):
        """List installed add-ons."""
        fake_addon = Addon(component=Component(project=Project()))
        for _unused, obj in sorted(ADDONS.items()):
            self.stdout.write(f".. _addon-{obj.name}:")
            self.stdout.write("\n")
            self.stdout.write(obj.verbose)
            self.stdout.write("-" * len(obj.verbose))
            self.stdout.write("\n")
            self.stdout.write(f":Add-on ID: ``{obj.name}``")
            if obj.settings_form:
                form = obj(fake_addon).get_settings_form(None)
                table = [
                    (f"``{name}``", str(field.label), str(field.help_text))
                    for name, field in form.fields.items()
                ]
                prefix = ":Configuration: "
                name_width = max(len(row[0]) for row in table)
                label_width = max(len(row[1]) for row in table)
                help_text_width = max(len(row[2]) for row in table)
                name_row = "-" * (name_width + 2)
                label_row = "-" * (label_width + 2)
                help_text_row = "-" * (help_text_width + 2)
                for name, label, help_text in table:
                    if not prefix.isspace():
                        self.stdout.write(
                            f"{prefix}+{name_row}+{label_row}+{help_text_row}+"
                        )
                        prefix = "                "
                    self.stdout.write(
                        f"{prefix}| {name:<{name_width}s} | {label:<{label_width}s} | {help_text:<{help_text_width}s} |"
                    )
                    self.stdout.write(
                        f"{prefix}+{name_row}+{label_row}+{help_text_row}+"
                    )
            else:
                self.stdout.write(":Configuration: `This add-on has no configuration.`")
            self.stdout.write("\n")
            self.stdout.write("\n".join(wrap(obj.description, 79)))
            self.stdout.write("\n")
