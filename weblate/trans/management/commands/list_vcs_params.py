# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.utils.management.base import BaseCommand
from weblate.utils.rst import format_rst_string, format_table
from weblate.vcs.params import VCS_PARAMS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from weblate.utils.rst import CellType


class Command(BaseCommand):
    help = "List version control parameters"

    def format_vcs_backends(self, vcs_backends: Sequence[str]) -> str:
        if "*" in vcs_backends:
            return "All version control systems"
        return "\n".join(f"* ``{backend}``" for backend in vcs_backends)

    def get_help_text(self, param) -> str:
        result = []
        if param.help_text:
            result.append(format_rst_string(param.help_text))
        if param.choices:
            if result:
                result.append("")
            result.append("Available choices:")
            for value, description in param.choices:
                result.extend(
                    (
                        "",
                        (f"* ``{value}`` -- {format_rst_string(description)}").replace(
                            "\\", "\\\\"
                        ),
                    )
                )
        return "\n".join(result)

    def handle(self, *args, **options) -> None:
        """List version control parameters."""
        self.stdout.write("""..
   Partly generated using ./manage.py list_vcs_params\n
""")
        header = [
            "Parameter name",
            "Version control systems",
            "Label",
            "Help text",
        ]
        table: list[list[CellType]] = [
            [
                param.name,
                self.format_vcs_backends(param.get_scopes()),
                str(param.label),
                self.get_help_text(param),
            ]
            for param in VCS_PARAMS
        ]
        table.sort(key=lambda row: str(row[0]))
        for table_row in format_table(table, header):
            self.stdout.write(table_row)
