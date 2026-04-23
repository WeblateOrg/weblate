# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.core.management.base import CommandError

from weblate.checks.format import BaseFormatCheck
from weblate.checks.models import CHECKS
from weblate.formats.models import FILE_FORMATS
from weblate.utils.management.base import DocGeneratorCommand

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from weblate.checks.base import BaseCheck


def sorter(check: BaseCheck):
    if isinstance(check, BaseFormatCheck):
        pos = 1
    elif check.name < "Formatted strings":
        pos = 0
    else:
        pos = 2
    return (check.source, pos, check.name.lower())


def escape(text: StrOrPromise):
    return text.replace("\\", "\\\\")


EXTRA_ENABLE_FLAG_DESCRIPTION = {
    "rst-text": "Treat a text as an reStructuredText document, affects :ref:`check-same`.",
    "bbcode-text": "Treat a text as an Bulletin Board Code (BBCode) document, affects :ref:`check-same`.",
    "md-text": "Treat a text as a Markdown document, and provide Markdown syntax highlighting on the translation text area.",
    "auto-java-messageformat": "Treat a text as conditional Java MessageFormat, enabling :ref:`check-java-format` only when the source contains Java MessageFormat placeholders.",
    "auto-safe-html": "Treat a text as conditional HTML, enabling :ref:`check-safe-html` only for plain text or source strings that contain standard HTML markup or valid custom elements. This is useful for extended Markdown variants such as MDX, where angle-bracket syntax may not be HTML.",
    "url": "The string should consist of only a URL.",
}


class Command(DocGeneratorCommand):
    help = "List installed checks"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "-s",
            "--sections",
            nargs="*",
            choices=["flags", "checks"],
            help="Filter output by section. Can specify multiple sections. "
            "If not specified, all sections are shown.",
        )

    def build_check_section(self, check) -> list[str]:
        lines: list[str] = []
        check_class = check.__class__
        is_format = isinstance(check, BaseFormatCheck)
        lines.append(f".. _{check.doc_id}:\n")
        name = escape(check.name)
        lines.append(name)
        if is_format:
            lines.append("*" * len(name))
        else:
            lines.append("~" * len(name))
        if version_lines := check.get_versions_rst_lines():
            lines.extend(version_lines)
        lines.extend(("", f":Summary: {escape(check.description)}"))
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
            enable_flags: set[str] = {
                check.enable_string,
                *check.extra_enable_strings,
            }
            auto_enable_descriptions = [
                f"``{flag}``: {EXTRA_ENABLE_FLAG_DESCRIPTION[flag]}"
                for flag in sorted(enable_flags)
                if flag.startswith("auto-") and flag in EXTRA_ENABLE_FLAG_DESCRIPTION
            ]
            flags = ", ".join(f"``{flag}``" for flag in sorted(enable_flags))
            lines.append(":Trigger: This check needs to be enabled using a flag.")

            file_formats = ", ".join(
                f":ref:`{file_format.format_id}`"
                for file_format in FILE_FORMATS.values()
                if set(file_format.check_flags) & enable_flags
            )
            if file_formats:
                lines.append(
                    f":File formats automatically enabling this check: {file_formats}"
                )
            lines.append(f":Flag to enable: {flags}")
            if auto_enable_descriptions:
                lines.append(":Automatic flag behavior:")
                lines.extend(
                    f"    {description}" for description in auto_enable_descriptions
                )
        else:
            lines.append(
                ":Trigger: This check is always enabled but can be ignored using a flag."
            )
        lines.append(f":Flag to ignore: ``{check.ignore_string}``")
        return lines

    def handle(self, *args, **options) -> None:
        """List installed checks."""
        sections = set(options.get("sections", []) or [])
        show_all = not sections

        ignores: list[str] = []
        enables: dict[str, list[str]] = defaultdict(list)
        for check in sorted(CHECKS.values(), key=sorter):
            self.add_section(check.doc_id, self.build_check_section(check))
            ignores.extend(
                (
                    f"``{check.ignore_string}``",
                    f"    Skip the :ref:`{check.doc_id}` quality check.",
                )
            )
            if check.default_disabled:
                for flag in (check.enable_string, *check.extra_enable_strings):
                    enables[flag].append(check.doc_id)

        output_file = options.get("output")

        if output_file is not None and len(sections) != 1:
            msg = (
                "Using --output with list_checks requires exactly one "
                "--sections value to select which generated snippet to write."
            )
            raise CommandError(msg)

        if show_all or "checks" in sections:
            self.write_sections(output_file)

        self.sections.clear()
        if show_all or "flags" in sections:
            enable_lines = []
            for flag, checks in enables.items():
                if len(checks) == 0:
                    continue
                if len(checks) == 1:
                    enable_string = f"Enables the :ref:`{checks[0]}` quality check."
                else:
                    enable_string = f"Enables the {', '.join([f':ref:`{check}`' for check in checks[:-1]])} and :ref:`{checks[-1]}` quality checks."
                enable_lines.append(f"``{flag}``")
                if flag in EXTRA_ENABLE_FLAG_DESCRIPTION:
                    enable_lines.append(f"    {EXTRA_ENABLE_FLAG_DESCRIPTION[flag]}")
                enable_lines.append(f"    {enable_string}")

            self.add_section("check-flags-enables", enable_lines)

            self.add_section(
                "check-flags-ignores",
                ignores,
            )
            self.write_sections(output_file)
