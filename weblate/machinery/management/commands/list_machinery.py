# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.machinery.models import MACHINERY
from weblate.utils.management.base import DocGeneratorCommand
from weblate.utils.rst import format_table


class Command(DocGeneratorCommand):
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
        for _unused, obj in sorted(MACHINERY.items()):
            machinery_content = []
            machinery_content.extend(
                [
                    f".. _mt-{obj.get_identifier()}:",
                    "",
                    obj.name,
                    "-" * len(obj.name),
                    *obj.get_versions_rst_lines(),
                    "",
                    f":Service ID: ``{obj.get_identifier()}``",
                    f":Maximal score: {obj.max_score}",
                ]
            )
            features = []
            if obj.highlight_syntax:
                features.append(":ref:`placeables-mt`")
            if obj.glossary_support:
                features.append(":ref:`glossary-mt`")
            if obj.llm_context_support:
                features.append(":ref:`llm-translation-context`")
            if features:
                prefix = ":Advanced features: "
                for feature in features:
                    machinery_content.append(f"{prefix}* {feature}")
                    if not prefix.isspace():
                        prefix = " " * len(prefix)

            if obj.settings_form:
                form = obj.settings_form(obj)
                table: list[list[str | list[list[str]]]] = [
                    [f"``{name}``", str(field.label), self.get_help_text(field)]
                    for name, field in form.fields.items()
                ]
                prefix = ":Configuration: "
                for table_row in format_table(table, None):
                    table_row = table_row.strip(
                        "\n"
                    )  # self.write_sections() inserts newlines
                    machinery_content.append(f"{prefix}{table_row}")
                    if not prefix.isspace():
                        prefix = " " * len(prefix)
                machinery_content.append("")
            else:
                machinery_content.append(
                    ":Configuration: `This service has no configuration.`"
                )
            self.add_section(obj.get_identifier(), machinery_content)
        self.write_sections(options.get("output"))
