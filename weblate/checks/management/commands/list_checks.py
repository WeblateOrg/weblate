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

from weblate.checks.format import BaseFormatCheck
from weblate.checks.models import CHECKS
from weblate.utils.management.base import BaseCommand


def sorter(check):
    if isinstance(check, BaseFormatCheck):
        pos = 1
    elif check.name < "Formatted strings":
        pos = 0
    else:
        pos = 2
    return (check.source, pos, check.name.lower())


def escape(text):
    return text.replace("\\", "\\\\")


class Command(BaseCommand):
    help = "List installed checks"

    def flush_lines(self, lines):
        self.stdout.writelines(lines)
        lines.clear()

    def handle(self, *args, **options):
        """List installed checks."""
        ignores = []
        enables = []
        lines = []
        for check in sorted(CHECKS.values(), key=sorter):
            check_class = check.__class__
            is_format = isinstance(check, BaseFormatCheck)
            # Output immediately
            self.stdout.write(f".. _{check.doc_id}:\n")
            if not lines:
                lines.append("\n")
            name = escape(check.name)
            lines.append(name)
            if is_format:
                lines.append("*" * len(name))
            else:
                lines.append("~" * len(name))
            lines.append("\n")
            lines.append(f":Summary: {escape(check.description)}")
            if check.target:
                if check.ignore_untranslated:
                    lines.append(":Scope: translated strings")
                else:
                    lines.append(":Scope: all strings")
            if check.source:
                lines.append(":Scope: source strings")
            lines.append(
                f":Check class: ``{check_class.__module__}.{check_class.__qualname__}``"
            )
            if check.default_disabled:
                lines.append(f":Flag to enable: ``{check.enable_string}``")
            lines.append(f":Flag to ignore: ``{check.ignore_string}``")
            lines.append("\n")

            self.flush_lines(lines)

            ignores.append(f"``{check.ignore_string}``")
            ignores.append(f"    Skip the :ref:`{check.doc_id}` quality check.")
            if check.default_disabled:
                enables.append(f"``{check.enable_string}``")
                enables.append(f"    Enable the :ref:`{check.doc_id}` quality check.")

        self.stdout.write("\n")
        self.stdout.writelines(enables)
        self.stdout.writelines(ignores)
