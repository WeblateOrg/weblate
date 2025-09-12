# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import operator
from typing import TYPE_CHECKING

from weblate.trans.file_format_params import FILE_FORMATS_PARAMS
from weblate.utils.management.base import BaseCommand
from weblate.utils.rst import format_table

if TYPE_CHECKING:
    from collections.abc import Sequence


class Command(BaseCommand):
    help = "List file format parameters"

    def format_file_formats(self, file_formats: Sequence[str]) -> str:
        lines = [
            " ".join([f"``{f}``" for f in file_formats[i * 4 : (i + 1) * 4]])
            for i in range((len(file_formats) // 4) + 1)
        ]
        return "\n".join(lines)

    def get_help_text(self, param) -> str:
        result = []
        if param.help_text:
            result.append(str(param.help_text))
        if param.choices:
            if result:
                result.append("")
            result.append("Available choices:")
            for value, description in param.choices:
                result.extend(
                    (
                        "",
                        f"``{value}``".replace("\\", "\\\\"),
                        f"  {description}".replace("\\", "\\\\"),
                    )
                )
        return "\n".join(result)

    def handle(self, *args, **options) -> None:
        """List file format parameters."""
        self.stdout.write("""..
   Partly generated using ./manage.py list_file_format_params\n
""")
        header = [
            "Parameter name",
            "File formats",
            "Label",
            "Help text",
        ]
        table = sorted(
            [
                [
                    param.name,
                    self.format_file_formats(param.file_formats),
                    str(param.label),
                    self.get_help_text(param),
                ]
                for param in FILE_FORMATS_PARAMS
            ],
            key=operator.itemgetter(0),
        )
        for table_row in format_table(table, header):
            self.stdout.write(table_row)
