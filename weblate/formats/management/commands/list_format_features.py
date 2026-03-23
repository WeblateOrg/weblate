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

        def new_field_list_item(
            table, title: str, value: str | bool, comment: str | None = None
        ) -> None:
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            value = f"`{value}`" if value else ""
            table.append(f":{title}: {value}")
            if comment:
                table.append(f"   {comment}")

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
            output.extend(["Supported features", "++++++++++++++++++", ""])
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

            new_field_list_item(
                output, "Common extensions", ", ".join(get_extensions(file_format))
            )
            new_field_list_item(output, "Linguality", linguality, "See :ref:`bimono`")
            new_field_list_item(
                output,
                "Supports plural",
                file_format.supports_plural,
                "See :ref:`format-plurals`",
            )
            new_field_list_item(
                output,
                "Supports descriptions",
                file_format.supports_descriptions,
                "See :ref:`format-description`",
            )
            new_field_list_item(
                output,
                "Supports explanation",
                file_format.supports_explanation,
                "See :ref:`format-explanation`",
            )
            new_field_list_item(
                output,
                "Supports context",
                file_format.supports_context,
                "See :ref:`format-context`",
            )
            new_field_list_item(
                output,
                "Supports location",
                file_format.supports_location,
                "See :ref:`format-location`",
            )
            new_field_list_item(
                output,
                "Supports flags",
                file_format.supports_flags,
                "See :ref:`format-flags`",
            )
            new_field_list_item(
                output,
                "Additional states",
                ", ".join(
                    [str(state.label) for state in file_format.additional_states]
                ),
                "See :ref:`format-states`",
            )
            api_identifiers = [file_format.format_id]
            api_identifiers.extend(
                FORMAT_DOC_SNIPPETS_MERGES.get(file_format.format_id, [])
            )

            new_field_list_item(output, "API identifier", ", ".join(api_identifiers))

            new_field_list_item(
                output,
                "Supports read-only strings",
                file_format.supports_read_only,
                "See :ref:`read-only-strings`",
            )

            if not file_path.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)

            start_marker, end_marker = self.autogenerated_markers(
                f"format-features {format_id}"
            )
            output = self.insert_markers(output, start_marker, end_marker)
            output.append("")
            file_path.write_text("\n".join(output), encoding="utf-8")
