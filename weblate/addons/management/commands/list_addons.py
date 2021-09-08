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

from weblate.addons.events import EVENT_NAMES
from weblate.addons.models import ADDONS, Addon
from weblate.trans.models import Component, Project
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "List installed add-ons"

    @staticmethod
    def get_help_text(field, name):
        result = []
        if field.help_text:
            result.append(str(field.help_text))
        choices = getattr(field, "choices", None)
        if choices and name not in ("component", "engines", "file_format"):
            if result:
                result.append("")
            result.append("Available choices:")
            for value, name in choices:
                result.append("")
                result.append(f"``{value}`` -- {name}".replace("\\", "\\\\"))
        return result

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
                    (f"``{name}``", str(field.label), self.get_help_text(field, name))
                    for name, field in form.fields.items()
                ]
                prefix = ":Configuration: "
                name_width = max(len(name) for name, _label, _help_text in table)
                label_width = max(len(label) for _name, label, _help_text in table)
                help_text_width = max(
                    max(len(line) for line in help_text) if help_text else 0
                    for _name, _label, help_text in table
                )
                name_row = "-" * (name_width + 2)
                label_row = "-" * (label_width + 2)
                help_text_row = "-" * (help_text_width + 2)
                for name, label, help_text in table:
                    if not prefix.isspace():
                        self.stdout.write(
                            f"{prefix}+{name_row}+{label_row}+{help_text_row}+"
                        )
                        prefix = "                "
                    if not help_text:
                        line = ""
                        self.stdout.write(
                            f"{prefix}| {name:<{name_width}s} | {label:<{label_width}s} | {line:<{help_text_width}s} |"
                        )
                    for pos, line in enumerate(help_text):
                        if pos > 0:
                            name = label = ""
                        self.stdout.write(
                            f"{prefix}| {name:<{name_width}s} | {label:<{label_width}s} | {line:<{help_text_width}s} |"
                        )
                    self.stdout.write(
                        f"{prefix}+{name_row}+{label_row}+{help_text_row}+"
                    )
            else:
                self.stdout.write(":Configuration: `This add-on has no configuration.`")
            events = ", ".join(EVENT_NAMES[event] for event in obj.events)
            self.stdout.write(f":Triggers: {events}")
            self.stdout.write("\n")
            self.stdout.write("\n".join(wrap(obj.description, 79)))
            self.stdout.write("\n")
