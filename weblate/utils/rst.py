# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from itertools import zip_longest
from typing import TYPE_CHECKING

from django_stubs_ext import StrOrPromise

if TYPE_CHECKING:
    from collections.abc import Generator


def get_cell_length(text: StrOrPromise) -> int:
    """Get cell length handling newlines."""
    return max(len(part) for part in text.split("\n"))


def get_row_lines(row_fmt: str, row: list[StrOrPromise]) -> Generator[str]:
    """Generate row lines for row data expanding newlines."""
    data = [item.split("\n") for item in row]
    for output in zip_longest(*data, fillvalue=""):
        yield row_fmt.format(*output)


def format_table(
    table: list[list[StrOrPromise | list[list[StrOrPromise]]]], header: list[str]
) -> list[str]:
    """
    Format reStructuredText table.

    * The table is list of lists
    * Row spans can be achieved by nested list:
      [["cell", [["span row 1 cell 1", "span row 1 cell 2"], ["span row 2 cell 1", "span row 2 cell 2"]]]]
    * The cells can contain newlines
    """
    widths: list[int] = [len(item) for item in header]
    output: list[str] = []
    plain_cols: int = 0

    # Figure out widths
    for row_no, row in enumerate(table):
        for column, item in enumerate(row):
            if isinstance(item, StrOrPromise):
                if row_no == 0 and column == plain_cols:
                    plain_cols += 1
                # Direct value
                widths[column] = max(widths[column], get_cell_length(item))
            else:
                # Rowspan
                for span_row in item:
                    for span_column, span_item in enumerate(span_row):
                        widths[column + span_column] = max(
                            widths[column + span_column], get_cell_length(span_item)
                        )

    row_fmt = "| {} |\n".format(" | ".join(f"{{:{width}}}" for width in widths))
    separator = "+{}+\n".format("+".join("-" * (width + 2) for width in widths))

    output.append(separator)
    if any(header):
        output.extend(
            [
                row_fmt.format(*header),
                separator.replace("-", "="),
            ]
        )

    for row in table:
        row_data: list[str] = []
        span_data: list[list[str]] = []
        for item in row:
            if span_data:
                msg = "Span has to be the last element"
                raise ValueError(msg)
            if isinstance(item, StrOrPromise):
                row_data.append(item)
            else:
                span_data = item
        if not span_data:
            output.extend(get_row_lines(row_fmt, row_data))
        else:
            for span_index, span_row in enumerate(span_data):
                if span_index == 0:
                    output.extend(get_row_lines(row_fmt, [*row_data, *span_row]))
                else:
                    output.extend(
                        get_row_lines(row_fmt, [""] * len(row_data) + span_row)
                    )
                if span_index < len(span_data) - 1:
                    output.append(
                        "|{}+{}+\n".format(
                            "|".join(
                                " " * (width + 2) for width in widths[: len(row_data)]
                            ),
                            "+".join(
                                "-" * (width + 2) for width in widths[len(row_data) :]
                            ),
                        )
                    )
        output.append(separator)

    return output
