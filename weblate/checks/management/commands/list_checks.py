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


class Command(BaseCommand):
    help = "List installed checks"

    def flush_lines(self, lines):
        self.stdout.writelines(lines)
        lines.clear()

    def handle(self, *args, **options):
        """List installed checks."""
        ignores = []
        lines = []
        for check in sorted(CHECKS.values(), key=sorter):
            is_format = isinstance(check, BaseFormatCheck)
            if not is_format and lines:
                self.flush_lines(lines)
            # Output immediately
            self.stdout.write(f".. _{check.doc_id}:\n")
            if not lines:
                lines.append("\n")
            lines.append(str(check.name))
            if is_format:
                lines.append("*" * len(check.name))
            else:
                lines.append("~" * len(check.name))
            lines.append("\n")
            lines.append("\n".join(wrap(f"*{check.description}*", 79)))
            lines.append("\n")

            if not is_format:
                self.flush_lines(lines)

            ignores.append(f"``{check.ignore_string}``")
            ignores.append(f'    Skip the "{check.name}" quality check.')

        self.stdout.write("\n")
        self.stdout.writelines(ignores)
