# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from itertools import zip_longest
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Generator


def get_cell_length(text: str) -> int:
    """Get cell length handling newlines."""
    return max(len(part) for part in text.split("\n"))


def get_row_lines(row: list[str | None]) -> Generator[list[str]]:
    """Generate row lines for row data expanding newlines."""
    data = [[] if item is None else item.split("\n") for item in row]
    yield from zip_longest(*data, fillvalue="")


CellType = str | list[list["CellType"]]


def get_cell_widths(
    table: list[list[CellType]] | list[list[str]], *, existing: list[int] | None = None
) -> list[int]:
    """Find maximal table cell widths."""
    widths: dict[int, int] = defaultdict(int)
    if existing:
        widths.update(enumerate(existing))
    for row in table:
        for column, item in enumerate(row):
            if isinstance(item, str):
                # Direct value
                widths[column] = max(widths[column], get_cell_length(item))
            else:
                # Row span
                for span_column, span_width in enumerate(get_cell_widths(item)):
                    widths[column + span_column] = max(
                        widths[column + span_column], span_width
                    )
    # This relies on dict keeping order
    return list(widths.values())


def generate_table_cells(
    table: list[list[CellType]], widths: list[int]
) -> Generator[list[str | None]]:
    """
    Generate table cell data.

    Span cells are generated as None.
    """
    for row in table:
        row_output: list[str | None] = []
        for column, value in enumerate(row):
            value = row[column]
            if isinstance(value, str):
                row_output.append(value)
            else:
                row_spaces = [None] * len(row_output)
                for span_column, span_value in enumerate(
                    generate_table_cells(value, widths[column:])
                ):
                    if span_column == 0:
                        yield [*row_output, *span_value]
                    else:
                        yield [*row_spaces, *span_value]
                row_output = []
        if row_output:
            yield row_output


def render_line(
    widths: list[int], next_row: list[str | None] | None, *, border: str = "-"
) -> str:
    """Render table line with a given border."""
    parts: list[str] = []
    for column, width in enumerate(widths):
        if next_row is None or isinstance(next_row[column], str):
            parts.extend(("+", border * (width + 2)))
        else:
            parts.extend(("|", " " * (width + 2)))
    parts.append("+\n")
    return "".join(parts)


def render_table(
    cells: list[list[str | None]], widths: list[int], *, border: str = "-"
) -> Generator[str]:
    """Render table content."""
    parts: list[str] = []
    for row_number, row_data in enumerate(cells):
        for line in get_row_lines(row_data):
            for column, width in enumerate(widths):
                value = line[column]
                if value is None:
                    value = ""
                parts.append(f"| {value:{width}} ")
            parts.append("|\n")
            yield "".join(parts)
            parts = []
        yield render_line(
            widths,
            None if row_number == len(cells) - 1 else cells[row_number + 1],
            border=border,
        )


def format_table(table: list[list[CellType]], header: list[str] | None) -> list[str]:
    """
    Format reStructuredText table.

    * The table is list of lists.
    * Row spans can be achieved by nested list:
      [["cell", [["span row 1 cell 1", "span row 1 cell 2"], ["span row 2 cell 1", "span row 2 cell 2"]]]]
    * The cells can contain newlines.
    """
    # Get cells and header widths
    widths: list[int] = get_cell_widths(table)
    if header:
        widths = get_cell_widths([header], existing=widths)

    # Generate table cells
    table_cells = list(generate_table_cells(table, widths))

    output: list[str] = [
        # Render initial line
        render_line(widths, None),
    ]

    # Header
    if header:
        output.extend(
            render_table([cast("list[str | None]", header)], widths, border="=")
        )

    # Table content
    output.extend(render_table(table_cells, widths))

    return output
