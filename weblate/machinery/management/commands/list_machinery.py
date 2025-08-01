# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.machinery.models import MACHINERY
from weblate.utils.management.base import BaseCommand
from weblate.utils.rst import format_table


class Command(BaseCommand):
    help = "List installed machineries"

    @staticmethod
    def get_help_text(field) -> str:
        result = []
        if field.help_text:
            result.append(str(field.help_text))
        choices = getattr(field, "choices", None)
        if choices:
            if result:
                result.append("")
            result.append("Available choices:")
            for value, description in choices:
                result.extend(
                    ("", f"``{value}`` -- {description}".replace("\\", "\\\\"))
                )
        return "\n".join(result)

    def handle(self, *args, **options) -> None:
        """List installed add-ons."""
        self.stdout.write("""..
   Partly generated using ./manage.py list_machinery
""")
        for _unused, obj in sorted(MACHINERY.items()):
            self.stdout.write(f".. _mt-{obj.get_identifier()}:")
            self.stdout.write("\n")
            self.stdout.write(obj.name)
            self.stdout.write("-" * len(obj.name))
            self.stdout.write("\n")
            self.stdout.write(f":Service ID: ``{obj.get_identifier()}``")
            self.stdout.write(f":Maximal score: {obj.max_score}")
            if obj.settings_form:
                form = obj.settings_form(obj)
                table: list[list[str | list[list[str]]]] = [
                    [f"``{name}``", str(field.label), self.get_help_text(field)]
                    for name, field in form.fields.items()
                ]
                prefix = ":Configuration: "
                for table_row in format_table(table, [""] * 3):
                    self.stdout.write(f"{prefix}{table_row}")
                    if not prefix.isspace():
                        prefix = " " * len(prefix)
            else:
                self.stdout.write(
                    ":Configuration: `This service has no configuration.`"
                )
            self.stdout.write("\n")
            self.stdout.write("\n")
