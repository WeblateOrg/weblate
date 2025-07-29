# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from collections.abc import Iterable

from weblate.trans.format_params import FILE_FORMATS_PARAMS
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "List file format parameters"

    def format_file_formats(self, file_formats: Iterable[str]) -> str:
        return ", ".join([f"``{file_format}``" for file_format in file_formats])

    def handle(self, *args, **options) -> None:
        """List file format parameters."""
        self.stdout.write(".. list-table::\n")
        self.stdout.write("   :header-rows: 1\n\n")
        self.stdout.write("   * - Parameter name\n")
        self.stdout.write("     - Label\n")
        self.stdout.write("     - File formats\n")

        for param in FILE_FORMATS_PARAMS:
            self.stdout.write(f"   * - {param.name}\n")
            self.stdout.write(f"     - {param.label}\n")
            self.stdout.write(
                f"     - {self.format_file_formats(param.file_formats)}\n"
            )
