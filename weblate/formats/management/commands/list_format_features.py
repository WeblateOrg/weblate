# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from itertools import chain
from typing import TYPE_CHECKING

from django.core.management.base import CommandError

from weblate.formats.models import FILE_FORMATS
from weblate.utils.management.base import DocGeneratorCommand

if TYPE_CHECKING:
    from pathlib import Path

FORMAT_DOC_SNIPPETS_MERGES = {
    "xliff": [
        "apple-xliff",
        "plainxliff",
        "poxliff",
    ],
    "xliff2": [
        "xliff2-placeables",
    ],
    "subtitles": [
        "ass",
        "ssa",
        "sub",
    ],
    "csv": [
        "csv-multi",
        "csv-simple",
    ],
    "go-i18n-json": [
        "go-i18n-json-v2",
    ],
    "json": [
        "json-nested",
    ],
    "javaprop": [
        "xwiki-fullpage",
        "xwiki-java-properties",
        "xwiki-page-properties",
    ],
    "txt": [
        "mediawiki",
        "dokuwiki",
    ],
}


class Command(DocGeneratorCommand):
    help = "Update format features snippets"
    output_required = True

    def handle(self, *args, **options) -> None:
        snippets_dir: Path = options["output"]

        if not snippets_dir.is_dir():
            msg = f"Error: {snippets_dir} must be a directory"
            raise CommandError(msg)

        # ignore formats that are merged into other formats
        ignore_list = set(chain(*FORMAT_DOC_SNIPPETS_MERGES.values()))

        def new_list_table_row(
            lines, feature_name: str, value: str | bool, doc_link: str | None = ""
        ) -> None:
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            if not value:
                return

            doc_link = f":ref:`↗ <{doc_link}>`" if doc_link else ""

            lines.extend(
                [
                    f"   * - {feature_name} {doc_link}",
                    f"     - ``{value}``",
                ]
            )

        def get_extensions(file_format) -> set[str]:
            try:
                common_extensions = file_format.get_class().Extensions
            except AttributeError:
                # non TTKitFormat formats
                common_extensions = []
            common_extensions.append(file_format.extension())

            if file_format.format_id in FORMAT_DOC_SNIPPETS_MERGES:
                for similar_format in FORMAT_DOC_SNIPPETS_MERGES[file_format.format_id]:
                    common_extensions.extend(
                        get_extensions(FILE_FORMATS[similar_format])
                    )

            return set(common_extensions)

        for format_id, file_format in FILE_FORMATS.items():
            if format_id in ignore_list:
                continue
            file_path = snippets_dir / f"{format_id}-features.rst"
            output = []
            output.extend(
                [
                    ".. list-table:: Supported features",
                    "   :stub-columns: 1",
                    "",
                ]
            )

            match file_format.monolingual:
                case True:
                    linguality = "Monolingual"
                case False:
                    linguality = "Bilingual"
                case None:
                    linguality = "Both monolingual and bilingual"
                case _:
                    msg = f"Invalid monolinguality: {file_format.monolingual}"
                    raise ValueError(msg)

            new_list_table_row(
                output,
                "Common extensions",
                ", ".join(sorted(get_extensions(file_format))),
            )
            new_list_table_row(output, "Linguality", linguality, "bimono")
            new_list_table_row(
                output,
                "Supports plural",
                file_format.supports_plural,
                "format-plurals",
            )
            new_list_table_row(
                output,
                "Supports descriptions",
                file_format.supports_descriptions,
                "format-description",
            )
            new_list_table_row(
                output,
                "Supports explanation",
                file_format.supports_explanation,
                "format-explanation",
            )
            new_list_table_row(
                output,
                "Supports context",
                file_format.supports_context,
                "format-context",
            )
            new_list_table_row(
                output,
                "Supports location",
                file_format.supports_location,
                "format-location",
            )
            new_list_table_row(
                output,
                "Supports flags",
                file_format.supports_flags,
                "format-flags",
            )
            new_list_table_row(
                output,
                "Additional states",
                ", ".join(
                    sorted(
                        [str(state.label) for state in file_format.additional_states]
                    )
                ),
                "format-states",
            )
            api_identifiers = [file_format.format_id]
            api_identifiers.extend(
                FORMAT_DOC_SNIPPETS_MERGES.get(file_format.format_id, [])
            )

            new_list_table_row(
                output, "API identifier", ", ".join(sorted(api_identifiers))
            )

            new_list_table_row(
                output,
                "Supports read-only strings",
                file_format.supports_read_only,
                "read-only-strings",
            )

            if file_path.exists():
                lines = file_path.read_text(encoding="utf-8").splitlines()
            else:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                lines = []

            start_marker, end_marker = self.autogenerated_markers(
                f"format-features {format_id}"
            )
            output = self.insert_markers(output, start_marker, end_marker)
            lines = self.insert_content_in_lines(
                output,
                lines,
                start_marker,
                end_marker,
            )
            lines.append("")
            file_path.write_text("\n".join(lines), encoding="utf-8")
