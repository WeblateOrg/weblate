# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import operator
from collections.abc import Iterable
from itertools import zip_longest

from weblate.trans.file_format_params import FILE_FORMATS_PARAMS
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "List file format parameters"

    def format_file_formats(self, file_formats: Iterable[str]) -> list[str]:
        return [
            " ".join([f"``{f}``" for f in file_formats[i * 4 : (i + 1) * 4]])
            for i in range((len(file_formats) // 4) + 1)
        ]

    def get_help_text(self, param) -> list[str]:
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
        return result

    def handle(self, *args, **options) -> None:
        """List file format parameters."""
        table = sorted(
            [
                (
                    [param.name],
                    self.format_file_formats(param.file_formats),
                    [param.label],
                    self.get_help_text(param),
                )
                for param in FILE_FORMATS_PARAMS
            ],
            key=operator.itemgetter(0),
        )

        def max_string_length(list_of_lists):
            return max(len(s) for sublist in list_of_lists for s in sublist)

        name_width = max_string_length([row[0] for row in table])
        formats_width = max(len(s) for r in table for s in r[1])
        label_width = max_string_length([row[2] for row in table])
        help_width = max(len(s) for r in table for s in r[3])

        sep = f"+-{'-' * name_width}-+-{'-' * formats_width}-+-{'-' * label_width}-+-{'-' * help_width}-+"
        row = f"| {{:{name_width}}} | {{:{formats_width}}} | {{:{label_width}}} | {{:{help_width}}} |"

        self.stdout.write(sep + "\n")
        self.stdout.write(
            row.format("Parameter name", "File formats", "Label", "Help text")
        )
        self.stdout.write(sep.replace("-", "=") + "\n")
        for name, formats, label, help_text in table:
            for line in zip_longest(name, formats, label, help_text, fillvalue=""):
                self.stdout.write(row.format(*line) + "\n")
            self.stdout.write(sep + "\n")
