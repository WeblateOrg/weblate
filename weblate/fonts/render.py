# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Matplotlib based text and bitmap rendering helpers."""

# Matplotlib must be imported after its cache and backend environment is set.
# ruff: file-ignore[module-import-not-at-top-of-file]
# pylint: disable=wrong-import-position,wrong-import-order

from __future__ import annotations

import os
from contextlib import contextmanager, suppress
from dataclasses import replace
from functools import cache, lru_cache
from hashlib import sha256
from importlib import import_module
from io import BytesIO
from math import ceil
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, Literal

from unicode_segmentation_rs import graphemes, line_break_units

from weblate.utils.data import data_path
from weblate.utils.icons import find_static_file

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from matplotlib.backend_bases import RendererBase
    from matplotlib.figure import Figure
    from matplotlib.font_manager import FontEntry, FontProperties
    from matplotlib.transforms import Bbox


# Matplotlib reads these variables while importing. Weblate installations often
# run with a read-only home directory, so keep its generated cache alongside the
# other application caches and always select a noninteractive backend.
_matplotlib_cache = data_path("cache") / "matplotlib"

# Matplotlib also attempts this while importing, but doing it explicitly avoids
# its temporary-directory fallback on fresh installations. Permission and stale
# path errors remain non-fatal here so Django's system check can report them.
with suppress(OSError):
    _matplotlib_cache.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("MPLCONFIGDIR", str(_matplotlib_cache))
os.environ.setdefault("MPLBACKEND", "Agg")

try:
    _text_helpers: Any = import_module("matplotlib._text_helpers")
except ImportError:
    _text_helpers = None

from matplotlib import font_manager, patheffects
from matplotlib import (
    image as matplotlib_image,
)
from matplotlib.backends.backend_agg import (
    FigureCanvasAgg,
    RendererAgg,
)
from matplotlib.figure import Figure
from matplotlib.font_manager import (
    FontProperties,
)
from matplotlib.ft2font import (
    LoadFlags,
)
from matplotlib.lines import Line2D
from matplotlib.patches import (
    FancyBboxPatch,
    PathPatch,
    Rectangle,
)
from matplotlib.path import (
    Path as MatplotlibPath,
)
from matplotlib.textpath import TextPath
from matplotlib.transforms import (
    Affine2D,
    Bbox,
    IdentityTransform,
)

RENDER_DPI = 72
FONT_SCALE = 4 / 3

SOURCE_SANS_ALIAS = "Weblate Source Sans 3"
KURINTO_ALIASES = (
    "Weblate Kurinto Sans",
    "Weblate Kurinto Sans JP",
    "Weblate Kurinto Sans KR",
    "Weblate Kurinto Sans SC",
    "Weblate Kurinto Sans TC",
)

_SYNTHETIC_BOLD_ATTRIBUTE = "_weblate_synthetic_bold"
_SOFT_HYPHEN = "\u00ad"
_VISIBLE_HYPHEN = "\u2010"
_UPLOADED_FONT_CACHE_SIZE = 32

_RENDER_LOCK = RLock()

FontStyle = Literal["normal", "italic", "oblique"]

_NO_BREAK_CHARACTERS = frozenset(
    {
        "\u00a0",  # No-break space
        "\u2011",  # Non-breaking hyphen
        "\u2007",  # Figure space
        "\u202f",  # Narrow no-break space
        "\u2060",  # Word joiner
        "\ufeff",  # Zero-width no-break space
    }
)


@contextmanager
def rendering_lock() -> Iterator[None]:
    """Serialize access to Matplotlib's process-global font state."""
    with _RENDER_LOCK:
        yield


@cache
def configure_matplotlib() -> None:
    """Register the bundled fonts with Matplotlib's process-local manager."""
    source_root = Path(
        find_static_file("weblate_fonts/source-sans/ttf/SourceSans3-Regular.ttf")
    ).parent
    kurinto_root = Path(
        find_static_file("weblate_fonts/kurinto/ttf/KurintoSans-Rg.ttf")
    ).parent
    fonts = (
        (source_root / "SourceSans3-Light.ttf", SOURCE_SANS_ALIAS),
        (source_root / "SourceSans3-Regular.ttf", SOURCE_SANS_ALIAS),
        (source_root / "SourceSans3-Bold.ttf", SOURCE_SANS_ALIAS),
        (kurinto_root / "KurintoSans-Rg.ttf", KURINTO_ALIASES[0]),
        (kurinto_root / "KurintoSans-Bd.ttf", KURINTO_ALIASES[0]),
        (kurinto_root / "KurintoSansJP-Rg.ttf", KURINTO_ALIASES[1]),
        (kurinto_root / "KurintoSansJP-Bd.ttf", KURINTO_ALIASES[1]),
        (kurinto_root / "KurintoSansKR-Rg.ttf", KURINTO_ALIASES[2]),
        (kurinto_root / "KurintoSansKR-Bd.ttf", KURINTO_ALIASES[2]),
        (kurinto_root / "KurintoSansSC-Rg.ttf", KURINTO_ALIASES[3]),
        (kurinto_root / "KurintoSansSC-Bd.ttf", KURINTO_ALIASES[3]),
        (kurinto_root / "KurintoSansTC-Rg.ttf", KURINTO_ALIASES[4]),
        (kurinto_root / "KurintoSansTC-Bd.ttf", KURINTO_ALIASES[4]),
    )
    with rendering_lock():
        for font_path, alias in fonts:
            _add_font_alias(font_path, alias)


def _add_font(font_path: Path) -> list[FontEntry]:
    """Register a font and return all entries Matplotlib discovered in it."""
    manager = font_manager.fontManager
    first_new_entry = len(manager.ttflist)
    manager.addfont(font_path)
    return manager.ttflist[first_new_entry:]


def _add_font_alias(font_path: Path, alias: str) -> None:
    """Register a font under a deterministic family name."""
    manager = font_manager.fontManager
    entry = _add_font(font_path)[0]
    manager.ttflist.append(replace(entry, name=alias))


def _font_weight_number(weight: str | int) -> int:
    if isinstance(weight, str):
        return font_manager.weight_dict.get(weight.lower(), 400)
    return int(weight)


def _font_style(style: str) -> FontStyle:
    if style == "italic":
        return "italic"
    if style == "oblique":
        return "oblique"
    return "normal"


def _uploaded_font_alias(font: str, signature: tuple[tuple[str, int, int], ...]) -> str:
    """Return a stable alias for a selected uploaded font and its faces."""
    digest = sha256()
    for filename, mtime, size in signature:
        digest.update(filename.encode())
        digest.update(b"\0")
        digest.update(str(mtime).encode())
        digest.update(b"\0")
        digest.update(str(size).encode())
        digest.update(b"\0")
    return f"Weblate uploaded font {font} {digest.hexdigest()[:16]}"


def _uploaded_font_signature(
    font: str, font_siblings: Iterable[str]
) -> tuple[tuple[str, int, int], ...]:
    """Return a cache signature for the selected uploaded font faces."""
    selected_font = str(Path(font).resolve())
    selected_stat = Path(selected_font).stat()
    result = [(selected_font, selected_stat.st_mtime_ns, selected_stat.st_size)]
    for sibling in font_siblings:
        try:
            filename = str(Path(sibling).resolve())
            if filename == selected_font:
                continue
            stat = Path(filename).stat()
        except OSError:
            continue
        result.append((filename, stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(result))


@lru_cache(maxsize=_UPLOADED_FONT_CACHE_SIZE)
def _load_uploaded_font_files(
    font: str,
    signature: tuple[tuple[str, int, int], ...],
) -> tuple[tuple[str, tuple[FontEntry, ...]], ...]:
    """Load the selected uploaded font and any valid sibling faces."""
    result: list[tuple[str, tuple[FontEntry, ...]]] = []
    with rendering_lock():
        for filename, _mtime, _size in signature:
            try:
                entries = tuple(_add_font(Path(filename)))
            except (OSError, RuntimeError):
                if filename == font:
                    raise
                continue
            result.append((filename, entries))
    return tuple(result)


@lru_cache(maxsize=_UPLOADED_FONT_CACHE_SIZE)
def _register_uploaded_font_files(
    font: str, signature: tuple[tuple[str, int, int], ...]
) -> tuple[str, tuple[tuple[int, FontStyle], ...], int, FontStyle]:
    """Register an uploaded font and its same-family sibling faces."""
    alias = _uploaded_font_alias(font, signature)
    entries_by_filename = dict(_load_uploaded_font_files(font, signature))
    selected_entries = entries_by_filename[font]
    selected_entry = selected_entries[0]
    family = selected_entry.name
    matching_entries = [entry for entry in selected_entries if entry.name == family]
    matching_entries.extend(
        entry
        for filename, entries in entries_by_filename.items()
        if filename != font
        for entry in entries
        if entry.name == family
    )
    with rendering_lock():
        manager = font_manager.fontManager
        for entry in matching_entries:
            manager.ttflist.append(replace(entry, name=alias))
    faces = tuple(
        sorted(
            {
                (_font_weight_number(entry.weight), _font_style(entry.style))
                for entry in matching_entries
            }
        )
    )
    return (
        alias,
        faces,
        _font_weight_number(selected_entry.weight),
        _font_style(selected_entry.style),
    )


def _register_uploaded_font(
    font: str,
    font_siblings: tuple[str, ...],
) -> tuple[str, tuple[tuple[int, FontStyle], ...], int, FontStyle]:
    font_path = Path(font).resolve()
    resolved_font = str(font_path)
    return _register_uploaded_font_files(
        resolved_font,
        _uploaded_font_signature(resolved_font, font_siblings),
    )


def _synthetic_bold_linewidth(font_properties: FontProperties) -> float:
    """Return the stroke width used to emulate a missing bold face."""
    if not getattr(font_properties, _SYNTHETIC_BOLD_ATTRIBUTE, False):
        return 0
    return max(0.5, font_properties.get_size_in_points() / 24)


def get_font_properties(
    font: str,
    *,
    size: float,
    weight: int | None = 400,
    font_siblings: tuple[str, ...] = (),
) -> FontProperties:
    """Create font properties for a stored font path or a font family."""
    configure_matplotlib()
    normalized_weight = weight or 400
    style: FontStyle = "normal"
    synthetic_bold = False
    if Path(font).is_file():
        alias, available_faces, selected_weight, style = _register_uploaded_font(
            font, font_siblings
        )
        families = [alias, *KURINTO_ALIASES, "DejaVu Sans"]
        if weight is None:
            normalized_weight = selected_weight
        synthetic_bold = normalized_weight >= 600 and not any(
            available_weight >= 600 and available_style == style
            for available_weight, available_style in available_faces
        )
        if synthetic_bold:
            normalized_weight = 400
    elif font in {"sans", "sans-serif"}:
        families = [SOURCE_SANS_ALIAS, *KURINTO_ALIASES, "DejaVu Sans"]
    elif font == "Kurinto Sans":
        families = [*KURINTO_ALIASES, SOURCE_SANS_ALIAS, "DejaVu Sans"]
    elif font == "Source Sans 3":
        families = [SOURCE_SANS_ALIAS, *KURINTO_ALIASES, "DejaVu Sans"]
    else:
        families = [font, SOURCE_SANS_ALIAS, *KURINTO_ALIASES, "DejaVu Sans"]
    properties = FontProperties(
        family=families,
        size=size,
        style=style,
        weight=normalized_weight,
    )
    setattr(properties, _SYNTHETIC_BOLD_ATTRIBUTE, synthetic_bold)
    return properties


def create_figure(width: int, height: int, *, facecolor="none") -> Figure:
    """Create a pixel-sized Figure using the noninteractive Agg backend."""
    figure = Figure(
        figsize=(width / RENDER_DPI, height / RENDER_DPI),
        dpi=RENDER_DPI,
        facecolor=facecolor,
        frameon=True,
    )
    FigureCanvasAgg(figure)
    return figure


def create_image_figure(filename: str) -> Figure:
    """Create a figure with an image filling the pixel canvas."""
    image = matplotlib_image.imread(filename)
    height, width = image.shape[:2]
    figure = create_figure(width, height)
    figure.figimage(image, xo=0, yo=0, origin="upper")
    return figure


def draw_line(
    figure: Figure,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color,
    linewidth: float = 1,
) -> None:
    """Draw a line using coordinates measured from the image's top-left."""
    _width, height = figure.canvas.get_width_height()
    figure.add_artist(
        Line2D(
            (start[0], end[0]),
            (height - start[1], height - end[1]),
            color=color,
            linewidth=linewidth,
            transform=IdentityTransform(),
        )
    )


def draw_rectangle(
    figure: Figure,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    color,
    radius: float = 0,
) -> None:
    """Draw a filled rectangle using top-left pixel coordinates."""
    _figure_width, figure_height = figure.canvas.get_width_height()
    position = (x, figure_height - y - height)
    patch: FancyBboxPatch | Rectangle
    if radius:
        patch = FancyBboxPatch(
            position,
            width,
            height,
            boxstyle=f"round,pad=0,rounding_size={radius}",
            facecolor=color,
            edgecolor="none",
            transform=IdentityTransform(),
        )
    else:
        patch = Rectangle(
            position,
            width,
            height,
            facecolor=color,
            edgecolor="none",
            transform=IdentityTransform(),
        )
    figure.add_artist(patch)


def draw_outline_rectangle(
    figure: Figure,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    color,
    linewidth: float = 1,
) -> None:
    """Draw an outline rectangle using top-left pixel coordinates."""
    _figure_width, figure_height = figure.canvas.get_width_height()
    figure.add_artist(
        Rectangle(
            (x, figure_height - y - height),
            width,
            height,
            fill=False,
            edgecolor=color,
            linewidth=linewidth,
            transform=IdentityTransform(),
        )
    )


def create_clip_box(x: float, y: float, width: float, height: float) -> Bbox:
    """Create a display-coordinate clipping box."""
    return Bbox.from_bounds(x, y, width, height)


def get_renderer(width: int = 1, height: int = 1) -> RendererAgg:
    """Create a lightweight text renderer."""
    return RendererAgg(width, height, RENDER_DPI)


def split_explicit_lines(text: str) -> list[str]:
    """Split explicit line breaks while preserving trailing empty lines."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def measure_line(
    text: str,
    font_properties: FontProperties,
    *,
    spacing: float = 0,
    renderer: RendererBase | None = None,
) -> tuple[float, float]:
    """Measure an unwrapped line in pixels."""
    if renderer is None:
        renderer = get_renderer()
    # Matplotlib 3.11 routes this through FT2Font's libraqm-backed layout,
    # preserving contextual shaping and bidirectional ordering.
    width, height, descent = renderer.get_text_width_height_descent(
        text, font_properties, ismath=False
    )
    if spacing and text:
        font = _get_layout_font(font_properties)
        features = ("-liga", "-clig")
        if _layout_items(text, font, features=features) is not None:
            font.set_text(text, 0, flags=LoadFlags.NO_HINTING, features=features)
            width = font.get_width_height()[0] / 64
        cluster_count = len(graphemes(text, is_extended=True))
        width += max(0, cluster_count - 1) * spacing
    synthetic_bold_linewidth = _synthetic_bold_linewidth(font_properties)
    return (
        width + synthetic_bold_linewidth,
        height + descent + synthetic_bold_linewidth,
    )


def measure_multiline(
    lines: Iterable[str],
    font_properties: FontProperties,
    *,
    spacing: float = 0,
) -> tuple[int, int]:
    """Measure lines using the same metrics as a Matplotlib Text artist."""
    line_list = list(lines)
    if not line_list:
        line_list = [""]
    renderer = get_renderer()
    widths = [
        measure_line(line, font_properties, spacing=spacing, renderer=renderer)[0]
        for line in line_list
    ]

    # Text's multiline layout uses a stable line box which includes ascender and
    # descender room. Measure it through the artist instead of approximating it
    # from a particular glyph run.
    figure = Figure(dpi=RENDER_DPI)
    artist = figure.text(
        0,
        0,
        "\n".join(line_list),
        fontproperties=font_properties,
        linespacing=1,
        parse_math=False,
    )
    bbox = artist.get_window_extent(renderer)
    return (
        ceil(max(widths, default=0)),
        ceil(bbox.height + _synthetic_bold_linewidth(font_properties)),
    )


def wrap_text(
    text: str,
    width: int,
    font_properties: FontProperties,
    *,
    spacing: float = 0,
) -> list[str]:
    """Wrap text at Unicode line-break opportunities, retaining explicit breaks."""
    renderer = get_renderer()
    result: list[str] = []
    for paragraph in split_explicit_lines(text):
        if not paragraph:
            result.append("")
            continue
        unbroken = _prepare_wrapped_line(paragraph, break_selected=False)
        if (
            _measure_wrapped_line(
                unbroken,
                font_properties,
                spacing=spacing,
                renderer=renderer,
            )
            <= width
        ):
            result.append(unbroken)
            continue

        units = _wrapping_units(paragraph)
        start_index = 0
        while start_index < len(units):
            candidate_units: list[str] = []
            fitting_index = start_index
            fitting_line = ""
            paragraph_finished = False
            for index in range(start_index, len(units)):
                candidate_units.append(units[index])
                candidate = "".join(candidate_units)
                unbroken = _prepare_wrapped_line(
                    candidate,
                    break_selected=False,
                )
                unbroken_width = _measure_wrapped_line(
                    unbroken,
                    font_properties,
                    spacing=spacing,
                    renderer=renderer,
                )
                if index == len(units) - 1:
                    if unbroken_width <= width or index == start_index:
                        result.append(unbroken)
                        paragraph_finished = True
                    break

                prepared = _prepare_wrapped_line(
                    candidate,
                    break_selected=True,
                )
                prepared_width = (
                    unbroken_width
                    if prepared == unbroken
                    else _measure_wrapped_line(
                        prepared,
                        font_properties,
                        spacing=spacing,
                        renderer=renderer,
                    )
                )
                if prepared_width <= width:
                    fitting_index = index + 1
                    fitting_line = prepared
                elif unbroken_width > width:
                    break

            if paragraph_finished:
                break
            if fitting_index == start_index:
                fitting_index += 1
                fitting_line = _prepare_wrapped_line(
                    units[start_index],
                    break_selected=True,
                )
            result.append(fitting_line)
            start_index = fitting_index
    return result


def _wrapping_units(text: str) -> list[str]:
    """Return UAX #14 units without separating paragraph indentation."""
    units = line_break_units(text)
    if len(units) > 1 and _is_breakable_space(units[0]):
        units[1] = f"{units[0]}{units[1]}"
        del units[0]
    return units


def _measure_wrapped_line(
    text: str,
    font_properties: FontProperties,
    *,
    spacing: float,
    renderer: RendererBase,
) -> float:
    return measure_line(
        text,
        font_properties,
        spacing=spacing,
        renderer=renderer,
    )[0]


def _prepare_wrapped_line(text: str, *, break_selected: bool) -> str:
    """Render discretionary hyphens only when their break is selected."""
    soft_hyphen_break = break_selected and text.endswith(_SOFT_HYPHEN)
    if break_selected:
        text = _rstrip_breakable_space(text)
    text = text.replace(_SOFT_HYPHEN, "")
    if soft_hyphen_break:
        return f"{text}{_VISIBLE_HYPHEN}"
    return text


def _is_breakable_space(text: str) -> bool:
    return all(
        character.isspace() and character not in _NO_BREAK_CHARACTERS
        for character in text
    )


def _rstrip_breakable_space(text: str) -> str:
    """Strip trailing wrapping spaces without removing no-break spaces."""
    position = len(text) - 1
    while position >= 0 and _is_breakable_space(text[position]):
        position -= 1
    return text[: position + 1]


def _get_layout_font(font_properties: FontProperties):
    """Resolve a fallback-aware font object through Matplotlib's public API."""
    filenames: list[str] = []
    for family in font_properties.get_family():
        family_properties = font_properties.copy()
        family_properties.set_family([family])
        try:
            filename = font_manager.findfont(
                family_properties,
                fallback_to_default=False,
            )
        except ValueError:
            continue
        if filename not in filenames:
            filenames.append(filename)
    if not filenames:
        filenames.append(font_manager.findfont(font_properties))
    font = font_manager.get_font(filenames)
    font.set_size(font_properties.get_size_in_points(), RENDER_DPI)
    return font


def _layout_items(text: str, font, *, features: tuple[str, ...] | None = None):
    """Use Matplotlib's internal glyph layout behind a guarded adapter."""
    layout = getattr(_text_helpers, "layout", None)
    if layout is None:
        return None
    try:
        return list(layout(text, font, features=features))
    except (AttributeError, TypeError):
        return None


def _layout_item_cluster_indices(items, font) -> list[int]:
    """Map shaped glyph items to their visual grapheme-cluster index."""
    result: list[int] = []
    item_index = 0
    cluster_index = 0
    while item_index < len(items):
        cluster_text = items[item_index].char
        isolated_items = _layout_items(
            cluster_text,
            font,
            features=("-liga", "-clig"),
        )
        item_count = max(1, len(isolated_items or ()))
        matching_items = 1
        while (
            item_index + matching_items < len(items)
            and items[item_index + matching_items].char == cluster_text
        ):
            matching_items += 1
        item_count = min(item_count, matching_items, len(items) - item_index)
        result.extend([cluster_index] * item_count)
        cluster_index += len(graphemes(cluster_text, is_extended=True))
        item_index += item_count
    return result


def _private_tracked_path(
    text: str,
    font_properties: FontProperties,
    spacing: float,
) -> tuple[MatplotlibPath, float] | None:
    """Build a tracked path with Matplotlib internals when available."""
    font = _get_layout_font(font_properties)
    features = ("-liga", "-clig")
    items = _layout_items(text, font, features=features)
    if items is None:
        return None
    cluster_indices = _layout_item_cluster_indices(items, font)
    paths: list[MatplotlibPath] = []
    try:
        for cluster_index, item in zip(cluster_indices, items, strict=True):
            item.ft_object.load_glyph(item.glyph_index, flags=LoadFlags.NO_HINTING)
            vertices, codes = item.ft_object.get_path()
            path = MatplotlibPath(vertices, codes)
            paths.append(
                path.transformed(
                    Affine2D().translate(
                        item.x + cluster_index * spacing,
                        item.y,
                    )
                )
            )
    except (AttributeError, TypeError):
        return None
    if not paths:
        return MatplotlibPath([[0, 0]], [MatplotlibPath.MOVETO]), 0
    font.set_text(text, 0, flags=LoadFlags.NO_HINTING, features=features)
    width = (
        font.get_width_height()[0] / 64
        + max(0, len(graphemes(text, is_extended=True)) - 1) * spacing
    )
    return MatplotlibPath.make_compound_path(*paths), width


def _public_tracked_path(
    text: str,
    font_properties: FontProperties,
    spacing: float,
) -> tuple[MatplotlibPath, float]:
    """Build a tracked path using stable Matplotlib APIs as a fallback."""
    paths: list[MatplotlibPath] = []
    prefix = ""
    clusters = graphemes(text, is_extended=True)
    for index, cluster in enumerate(clusters):
        x = measure_line(prefix, font_properties)[0] + index * spacing
        paths.append(TextPath((x, 0), cluster, prop=font_properties))
        prefix = f"{prefix}{cluster}"
    if not paths:
        return MatplotlibPath([[0, 0]], [MatplotlibPath.MOVETO]), 0
    width = measure_line(text, font_properties)[0] + max(0, len(clusters) - 1) * spacing
    return MatplotlibPath.make_compound_path(*paths), width


def _tracked_path(
    text: str,
    font_properties: FontProperties,
    spacing: float,
) -> tuple[MatplotlibPath, float]:
    """Return a fully shaped glyph path with tracking applied between glyphs."""
    private_result = _private_tracked_path(text, font_properties, spacing)
    if private_result is not None:
        return private_result
    return _public_tracked_path(text, font_properties, spacing)


def draw_text(
    figure: Figure,
    x: float,
    y: float,
    text: str,
    *,
    font_properties: FontProperties,
    color,
    horizontalalignment: Literal["left", "center", "right"] = "left",
    verticalalignment: Literal["top", "center", "baseline", "bottom"] = "top",
    spacing: float = 0,
    clip_box: Bbox | None = None,
) -> None:
    """Draw text using pixel coordinates measured from the image's top-left."""
    text = "\n".join(split_explicit_lines(text))
    width, height = figure.canvas.get_width_height()
    if not spacing:
        artist = figure.text(
            x / width,
            1 - y / height,
            text,
            color=color,
            fontproperties=font_properties,
            horizontalalignment=horizontalalignment,
            verticalalignment=verticalalignment,
            linespacing=1,
            parse_math=False,
        )
        synthetic_bold_linewidth = _synthetic_bold_linewidth(font_properties)
        if synthetic_bold_linewidth:
            artist.set_path_effects(
                [
                    patheffects.withStroke(
                        linewidth=synthetic_bold_linewidth,
                        foreground=color,
                    )
                ]
            )
        if clip_box is not None:
            artist.set_clip_on(True)
            artist.set_clip_box(clip_box)
        return

    lines = split_explicit_lines(text)
    _unused_width, line_height = measure_multiline(["Ag"], font_properties)
    for line_number, line in enumerate(lines):
        if not line:
            continue
        path, path_width = _tracked_path(line, font_properties, spacing)
        line_x = x
        if horizontalalignment == "center":
            line_x -= path_width / 2
        elif horizontalalignment == "right":
            line_x -= path_width

        renderer = get_renderer()
        _line_width, glyph_height, descent = renderer.get_text_width_height_descent(
            line or "Ag", font_properties, ismath=False
        )
        if verticalalignment == "top":
            baseline_from_top = glyph_height - descent
        elif verticalalignment == "center":
            baseline_from_top = (glyph_height - descent) / 2
        elif verticalalignment == "bottom":
            baseline_from_top = -descent
        else:
            baseline_from_top = 0
        baseline_y = height - y - baseline_from_top - line_number * line_height
        patch = PathPatch(
            path,
            facecolor=color,
            edgecolor=(color if _synthetic_bold_linewidth(font_properties) else "none"),
            linewidth=_synthetic_bold_linewidth(font_properties),
            transform=Affine2D().translate(line_x, baseline_y) + IdentityTransform(),
        )
        if clip_box is not None:
            patch.set_clip_on(True)
            patch.set_clip_box(clip_box)
        figure.add_artist(patch)


def figure_to_png(figure: Figure, output=None) -> bytes:
    """Render a figure as PNG, optionally writing it to a file-like object."""
    canvas = figure.canvas
    if not isinstance(canvas, FigureCanvasAgg):
        canvas = FigureCanvasAgg(figure)
    if output is None:
        target = BytesIO()
        canvas.print_png(target)
        return target.getvalue()
    canvas.print_png(output)
    return b""
