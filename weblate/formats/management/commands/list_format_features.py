# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from itertools import chain
from pathlib import Path

from django.core.management.base import CommandError

from weblate.formats.models import FILE_FORMATS
from weblate.utils.management.base import DocGeneratorCommand

FORMAT_DOC_SNIPPETS_MERGES = {
    "xliff": [
        "apple-xliff",
        "plainxliff",
        "poxliff",
        "xliff2",
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
}


class Command(DocGeneratorCommand):
    help = "Update format features snippets"
    output_required = True

    def handle(self, *args, **options) -> None:
        # TODO: add a check option to check if all the generated files are included in a doc file
        snippets_dir: Path = options["output"]

        if not snippets_dir.is_dir():
            msg = f"Error: {snippets_dir} must be a directory"
            raise CommandError(msg)

        # ignore formats that are merged into other formats
        ignore_list = set(chain(*FORMAT_DOC_SNIPPETS_MERGES.values()))

        def new_row(table, *columns: str) -> None:
            output.extend(
                [
                    f"   * - {columns[0]}",
                    *[f"     - {column}" for column in columns[1:]],
                ]
            )

        def yes_no_row(table: list[str], title: str, value: bool) -> None:
            new_row(table, title, "Yes" if value else "No")

        def get_extensions(file_format) -> set[str]:
            try:
                common_extensions = file_format.get_class().Extensions
            except AttributeError:
                # non TTKitFormat formats
                common_extensions = [file_format.extension()]

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
            output.append(".. list-table:: Supported features\n")
            match file_format.monolingual:
                case True:
                    linguality = "mono"
                case False:
                    linguality = "bilingual"
                case None:
                    linguality = "both"
                case _:
                    msg = f"Invalid monolinguality: {file_format.monolingual}"
                    raise ValueError(msg)

            new_row(output, "Common extensions", ", ".join(get_extensions(file_format)))
            new_row(output, "Linguality [#m]_", linguality)
            yes_no_row(output, "Supports plural [#p]_", file_format.supports_plural)
            yes_no_row(
                output, "Supports descriptions [#n]_", file_format.supports_descriptions
            )
            yes_no_row(output, "Supports context [#c]_", file_format.supports_context)
            yes_no_row(output, "Supports location [#l]_", file_format.supports_location)
            yes_no_row(output, "Supports flags [#f]_", file_format.supports_flags)
            new_row(
                output,
                "Additional states [#a]_",
                ", ".join(
                    [str(state.label) for state in file_format.additional_states]
                ),
            )
            api_identifiers = [file_format.format_id]
            api_identifiers.extend(
                FORMAT_DOC_SNIPPETS_MERGES.get(file_format.format_id, [])
            )

            new_row(output, "API identifier", ", ".join(api_identifiers))

            yes_no_row(
                output,
                "Supports read-only strings [#r]_",
                file_format.supports_read_only,
            )

            output.extend(
                [
                    "",
                    ".. [#m] See :ref:`bimono`",
                    ".. [#p] See :ref:`format-plurals`",
                    ".. [#n] See :ref:`format-description`",
                    ".. [#c] See :ref:`format-context`",
                    ".. [#l] See :ref:`format-location`",
                    ".. [#a] See :ref:`format-states`",
                    ".. [#f] See :ref:`format-flags`.",
                    ".. [#r] See :ref:`read-only-strings`.",
                ]
            )

            if not file_path.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)

            start_marker, end_marker = self.autogenerated_markers(
                f"format-features {format_id}"
            )
            output = self.insert_markers(output, start_marker, end_marker)

            Path(file_path).write_text("\n".join(output), encoding="utf-8")
