# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.checks.format import BaseFormatCheck
from weblate.checks.models import CHECKS
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from weblate.checks.base import BaseCheck


def sorter(check: BaseCheck):
    if isinstance(check, BaseFormatCheck):
        pos = 1
    elif check.name < "Formatted strings":
        pos = 0
    else:
        pos = 2
    return (check.source, pos, check.name.lower())


def escape(text: str):
    return text.replace("\\", "\\\\")


class Command(BaseCommand):
    help = "List installed checks"

    def flush_lines(self, lines: list[str]) -> None:
        self.stdout.writelines(lines)
        lines.clear()

    def handle(self, *args, **options) -> None:
        """List installed checks."""
        ignores: list[str] = []
        enables: list[str] = []
        lines: list[str] = []
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
            lines.extend(("\n", f":Summary: {escape(check.description)}"))
            if check.glossary:
                lines.append(":Scope: glossary strings")
            elif check.target:
                if check.ignore_untranslated:
                    lines.append(":Scope: translated strings")
                else:
                    lines.append(":Scope: all strings")
            elif check.source:
                lines.append(":Scope: source strings")
            lines.extend(
                (
                    f":Check class: ``{check_class.__module__}.{check_class.__qualname__}``",
                    f":Check identifier: ``{check.check_id}``",
                )
            )
            if check.default_disabled:
                flags = ", ".join(
                    f"``{flag}``"
                    for flag in [check.enable_string, *check.extra_enable_strings]
                )
                lines.append(f":Flag to enable: {flags}")
            lines.extend((f":Flag to ignore: ``{check.ignore_string}``", "\n"))

            self.flush_lines(lines)

            ignores.extend(
                (
                    f"``{check.ignore_string}``",
                    f"    Skip the :ref:`{check.doc_id}` quality check.",
                )
            )
            if check.default_disabled:
                enables.extend(
                    (
                        f"``{check.enable_string}``",
                        f"    Enable the :ref:`{check.doc_id}` quality check.",
                    )
                )

        self.stdout.write("\n")
        self.stdout.writelines(enables)
        self.stdout.writelines(ignores)
