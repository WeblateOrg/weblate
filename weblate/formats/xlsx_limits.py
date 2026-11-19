# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Budgets for XLSX archive expansion and CSV conversion."""

from __future__ import annotations

from typing import TYPE_CHECKING
from zipfile import ZipFile

from django.utils.translation import gettext

from weblate.formats.limits import TranslationLimitError
from weblate.utils.zip import ZipSafetyError, ZipSafetyLimits, validate_zip_member_count

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import BinaryIO

XLSX_READ_CHUNK_SIZE = 64 * 1024
XLSX_TEXT_CHUNK_SIZE = 16 * 1024


def validate_xlsx_archive(storefile: str | BinaryIO, max_size: int) -> None:
    """Bound declared and actual expanded bytes before openpyxl loads metadata."""
    with ZipFile(storefile) as archive:
        try:
            validate_zip_member_count(archive, limits=ZipSafetyLimits())
        except ZipSafetyError as error:
            raise TranslationLimitError(str(error)) from error
        if sum(info.file_size for info in archive.infolist()) > max_size:
            raise TranslationLimitError(
                gettext(
                    "Workbook archive exceeds the maximum expanded size of %d bytes."
                )
                % max_size
            )
        expanded = 0
        for info in archive.infolist():
            with archive.open(info) as member:
                while chunk := member.read(
                    min(XLSX_READ_CHUNK_SIZE, max_size - expanded + 1)
                ):
                    expanded += len(chunk)
                    if expanded > max_size:
                        raise TranslationLimitError(
                            gettext(
                                "Workbook archive exceeds the maximum expanded size of %d bytes."
                            )
                            % max_size
                        )


def prepare_xlsx_csv_row(
    values: Iterable[object], remaining_bytes: int
) -> tuple[list[str], int]:
    """Measure a QUOTE_ALL UTF-8 CSV row before allocating the joined output."""
    result: list[str] = []
    size = 1  # Unix dialect line terminator.
    for value in values:
        text = "" if value is None else str(value)
        overhead = 2 + bool(result)  # Quotes and optional comma.
        # Character count is a cheap lower bound before scanning a large cell.
        if size + len(text) + overhead > remaining_bytes:
            raise TranslationLimitError(
                gettext("Converted workbook content exceeds the configured size limit.")
            )
        size += overhead
        for position in range(0, len(text), XLSX_TEXT_CHUNK_SIZE):
            chunk = text[position : position + XLSX_TEXT_CHUNK_SIZE]
            size += len(chunk.encode("utf-8")) + chunk.count('"')
            if size > remaining_bytes:
                raise TranslationLimitError(
                    gettext(
                        "Converted workbook content exceeds the configured size limit."
                    )
                )
        result.append(text)
    if size > remaining_bytes:
        raise TranslationLimitError(
            gettext("Converted workbook content exceeds the configured size limit.")
        )
    return result, size
