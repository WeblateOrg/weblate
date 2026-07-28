# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os.path
from math import ceil
from typing import TYPE_CHECKING, ClassVar, Literal, NotRequired, TypedDict

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.text import capfirst
from django.utils.translation import (
    get_language,
    get_language_bidi,
    gettext,
    gettext_lazy,
    ngettext,
    npgettext,
    pgettext,
    pgettext_lazy,
)

from weblate.fonts.render import (
    FONT_SCALE,
    create_figure,
    create_image_figure,
    draw_line,
    draw_rectangle,
    draw_text,
    figure_to_png,
    get_font_properties,
    measure_line,
    rendering_lock,
)
from weblate.fonts.utils import render_size
from weblate.lang.models import Language
from weblate.trans.models import Component, Project
from weblate.trans.templatetags.translations import number_format
from weblate.trans.util import sort_unicode, translation_percent
from weblate.utils import messages
from weblate.utils.icons import find_static_file
from weblate.utils.site import get_site_url
from weblate.utils.stats import (
    GlobalStats,
    ProjectLanguage,
    ProjectLanguageStats,
    TranslationStats,
    get_non_glossary_stats,
)
from weblate.utils.views import get_percent_color

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse
    from django_stubs_ext import StrOrPromise
    from matplotlib.font_manager import FontProperties

    from weblate.utils.stats import (
        BaseStats,
    )

COLOR_DATA = {
    "grey": (0, 0, 0),
    "white": (0, 0, 0),
    "black": (255, 255, 255),
    "graph": (255, 255, 255),
}

WIDGETS: dict[str, type[Widget]] = {}
WIDGET_FONT = "Source Sans 3"
# Pango rounded the Source Sans ascent and descent independently. Preserve
# those logical line metrics because the bitmap backgrounds were designed for
# their resulting baselines.
WIDGET_FONT_ASCENT = 1.02
WIDGET_FONT_DESCENT = 0.4
PNG_BADGE_FONT_SIZE = 11
PNG_BADGE_BASELINE = 14


def get_widget_text_metrics(font_properties: FontProperties) -> tuple[int, int]:
    """Return baseline and line height matching the former Pango layout."""
    size = font_properties.get_size_in_points()
    baseline = ceil(size * WIDGET_FONT_ASCENT)
    return baseline, baseline + ceil(size * WIDGET_FONT_DESCENT)


def register_widget(widget):
    """Register widget in dictionary."""
    WIDGETS[widget.name] = widget
    return widget


class ExtraParametersDict(TypedDict):
    name: str
    label: StrOrPromise
    type: Literal["number", "boolean"]
    default: int | bool
    min: NotRequired[int]
    max: NotRequired[int]
    step: NotRequired[int]


class MatrixCellDict(TypedDict):
    name: str
    percent: int
    progress_percent: float
    color: str
    url: str
    x: NotRequired[int]
    y: NotRequired[int]
    label_x: NotRequired[int]
    percent_x: NotRequired[int]
    text_y: NotRequired[int]
    label: NotRequired[str]
    progress_width: NotRequired[int]


class Widget:
    """Generic widget class."""

    name = ""
    verbose: StrOrPromise = ""
    colors: tuple[str, ...] = ()
    extension = "png"
    content_type = "image/png"
    order = 100
    extra_parameters: ClassVar[list[ExtraParametersDict]] = []

    def __init__(self, obj, color=None, lang=None) -> None:
        """Create Widget object."""
        # Get object and related params
        self.obj = obj
        self.color = self.get_color_name(color)
        self.lang = lang
        if obj is None:
            stats = GlobalStats()
        elif lang:
            stats = obj.stats.get_single_language_stats(lang)
        else:
            stats = obj.stats
        self.stats = stats
        self.non_glossary_stats = get_non_glossary_stats(stats)
        self.percent = translation_percent(
            self.non_glossary_stats["translated"], self.non_glossary_stats["all"]
        )

    def get_color_name(self, color):
        """Return color name based on allowed ones."""
        if color not in self.colors:
            return self.colors[0]
        return color

    def get_percent_text(self):
        return pgettext("Translated percents", "%(percent)s%%") % {
            "percent": int(self.percent)
        }

    def render(self, request: HttpRequest, response: HttpResponse) -> None:
        raise NotImplementedError


class BitmapWidget(Widget):
    """Base class for bitmap rendering widgets."""

    colors: tuple[str, ...] = ("grey", "white", "black")
    extension = "png"
    content_type = "image/png"
    order = 100
    font_size = 10
    line_spacing = 1.0
    head_spacing = -0.5
    foot_spacing = 1
    offset = 0
    column_offset = 0
    lines = True

    def __init__(self, obj, color=None, lang=None) -> None:
        """Create Widget object."""
        super().__init__(obj, color, lang)
        # Get object and related params
        if isinstance(self.stats, TranslationStats):
            self.total = self.non_glossary_stats["all"]
        else:
            self.total = self.non_glossary_stats["source_strings"]
        self.languages = self.stats.languages
        self.params = self.get_text_params()

        # Set rendering variables
        self.draw = None
        self.width = 0

    def get_text_params(self):
        """Create dictionary used for text formatting."""
        return {
            "name": self.obj.name if self.obj else settings.SITE_TITLE,
            "count": self.total,
            "languages": self.languages,
            "percent": self.percent,
        }

    def get_filename(self):
        """Return widgets filename."""
        return find_static_file(
            os.path.join(
                "widget-images",
                f"{self.name}-{self.color}.png",
            )
        )

    def get_columns(self) -> list[list[str]]:
        raise NotImplementedError

    def get_column_width(self, width, columns):
        return width // len(columns)

    def get_column_fonts(self):
        return [
            get_font_properties(
                WIDGET_FONT, size=self.font_size * 1.5 * FONT_SCALE, weight=700
            ),
            get_font_properties(
                WIDGET_FONT, size=self.font_size * FONT_SCALE, weight=400
            ),
        ]

    def render_additional(self, figure) -> None:
        return

    def render(self, request: HttpRequest, response: HttpResponse) -> None:
        """Render widget."""
        with rendering_lock():
            figure = create_image_figure(self.get_filename())
            width, height = figure.canvas.get_width_height()
            columns = self.get_columns()
            column_width = self.get_column_width(width, columns)
            fonts = self.get_column_fonts()

            for column_number, column in enumerate(columns):
                offset = float(self.offset)
                center = (
                    self.column_offset + column_width * column_number + column_width / 2
                )
                for row, text in enumerate(column):
                    font_properties = fonts[row]
                    baseline, line_height = get_widget_text_metrics(font_properties)
                    draw_text(
                        figure,
                        center,
                        offset + baseline,
                        str(text),
                        font_properties=font_properties,
                        color=tuple(value / 255 for value in COLOR_DATA[self.color]),
                        horizontalalignment="center",
                        verticalalignment="baseline",
                        spacing=self.head_spacing if row == 0 else self.foot_spacing,
                    )
                    offset += line_height * self.line_spacing

                if self.lines and column_number > 0:
                    draw_line(
                        figure,
                        (column_width * column_number, self.offset),
                        (column_width * column_number, height - self.offset),
                        color=tuple(value / 255 for value in COLOR_DATA[self.color]),
                        linewidth=0.5,
                    )

            self.render_additional(figure)
            figure_to_png(figure, response)


class SVGWidget(Widget):
    """Base class for SVG rendering widgets."""

    extension = "svg"
    content_type = "image/svg+xml; charset=utf-8"
    template_name = ""

    def render(self, request: HttpRequest, response: HttpResponse) -> None:
        raise NotImplementedError


@register_widget
class NormalWidget(BitmapWidget):
    name = "287x66"
    order = 110
    offset = 10
    # Translators: status widget name
    verbose = gettext_lazy("Big status badge")

    def get_columns(self):
        return [
            [
                number_format(self.total),
                npgettext(
                    "Label on engage page", "String", "Strings", self.total
                ).upper(),
            ],
            [
                number_format(self.languages),
                npgettext(
                    "Label on engage page", "Language", "Languages", self.languages
                ).upper(),
            ],
            [
                self.get_percent_text(),
                gettext("Translated").upper(),
            ],
        ]


@register_widget
class SmallWidget(BitmapWidget):
    name = "88x31"
    order = 111
    font_size = 7
    line_spacing = 0.8
    offset = -1
    # Translators: status widget name
    verbose = gettext_lazy("Small status badge")

    def get_columns(self):
        return [
            [
                self.get_percent_text(),
                gettext("Translated").upper(),
            ]
        ]


@register_widget
class OpenGraphWidget(NormalWidget):
    name = "open"
    colors: tuple[str, ...] = ("graph",)
    order = 120
    lines = False
    offset = 300
    font_size = 20
    column_offset = 265
    head_spacing = -1
    foot_spacing = 2
    verbose = pgettext_lazy("Status widget name", "Panel")

    def get_column_width(self, width, columns) -> int:
        return 230

    def get_column_fonts(self):
        return [
            get_font_properties(WIDGET_FONT, size=42 * FONT_SCALE, weight=400),
            get_font_properties(WIDGET_FONT, size=18 * FONT_SCALE, weight=400),
        ]

    def get_name(self) -> str:
        if self.obj is None:
            return settings.SITE_TITLE
        return str(self.obj)

    def get_title_parts(self, name: str, suffix: str = "") -> tuple[str, str, str]:
        if self.obj is None:
            template = "{}"
        elif isinstance(self.obj, Project):
            # Translators: Text on OpenGraph image
            template = gettext("Project {}")
        else:
            # Translators: Text on OpenGraph image
            template = gettext("Component {}")

        prefix, placeholder, postfix = template.partition("{}")
        if not placeholder:
            return template, "", ""
        return prefix, name, f"{suffix}{postfix}"

    @staticmethod
    def get_title_runs(
        title_parts: tuple[str, str, str],
        regular_font: FontProperties,
        bold_font: FontProperties,
    ) -> list[tuple[str, FontProperties]]:
        """Return styled title runs in visual locale order."""
        runs = list(
            zip(
                title_parts,
                (regular_font, bold_font, regular_font),
                strict=True,
            )
        )
        if get_language_bidi():
            runs.reverse()
        return runs

    def render_additional(self, figure) -> None:
        font_size = 52 * FONT_SCALE
        regular_font = get_font_properties(WIDGET_FONT, size=font_size, weight=400)
        bold_font = get_font_properties(WIDGET_FONT, size=font_size, weight=700)
        name = self.get_name()
        title_parts = self.get_title_parts(name)

        max_width = 1200 - 280
        while (
            sum(
                measure_line(text, font_properties)[0]
                for text, font_properties in self.get_title_runs(
                    title_parts,
                    regular_font,
                    bold_font,
                )
            )
            > max_width
        ):
            if " " in name:
                name = name.rsplit(" ", 1)[0]
            elif "-" in name:
                name = name.rsplit("-", 1)[0]
            elif "_" in name:
                name = name.rsplit("_", 1)[0]
            else:
                name = name[:-1]
            title_parts = self.get_title_parts(name, "…")
            if not name:
                break

        x = 280.0
        baseline = 170 + get_widget_text_metrics(bold_font)[0]
        for text, font_properties in self.get_title_runs(
            title_parts,
            regular_font,
            bold_font,
        ):
            if not text:
                continue
            draw_text(
                figure,
                x,
                baseline,
                text,
                font_properties=font_properties,
                color=(1, 1, 1),
                verticalalignment="baseline",
            )
            x += measure_line(text, font_properties)[0]


class BaseSVGBadgeWidget(SVGWidget):
    colors: tuple[str, ...] = ("badge",)
    template_name = "svg/badge.svg"

    def render_badge(
        self, response: HttpResponse, label: str, value: str, color: str
    ) -> None:
        label_width = render_size(f"   {label}   ")[0].width
        value_width = render_size(f"  {value}  ")[0].width

        response.write(
            render_to_string(
                self.template_name,
                {
                    "label": label,
                    "value": value,
                    "label_width": label_width,
                    "value_width": value_width,
                    "width": label_width + value_width,
                    "color": color,
                    "translated_offset": label_width // 2,
                    "percent_offset": label_width + value_width // 2,
                    "lang": get_language(),
                    "fonts_cdn_url": settings.FONTS_CDN_URL,
                },
            )
        )


@register_widget
class SVGBadgeWidget(BaseSVGBadgeWidget):
    name = "svg"
    order = 80
    # Translators: status widget name
    verbose = gettext_lazy("SVG status badge")
    extra_parameters: ClassVar[list[ExtraParametersDict]] = [
        {
            "name": "capitalize",
            "label": gettext_lazy("Capitalize"),
            "type": "boolean",
            "default": False,
        }
    ]

    def get_badge_data(self, request: HttpRequest) -> tuple[str, str, str]:
        translated_text = str(gettext("translated"))
        if request.GET.get("capitalize") == "1":
            translated_text = str(capfirst(translated_text))
        percent_text = self.get_percent_text()
        if self.percent >= 90:
            color = "#4c1"
        elif self.percent >= 75:
            color = "#dfb317"
        else:
            color = "#e05d44"
        return translated_text, percent_text, color

    def render(self, request: HttpRequest, response: HttpResponse) -> None:
        self.render_badge(response, *self.get_badge_data(request))


@register_widget
class PNGBadgeWidget(SVGBadgeWidget):
    name = "status"
    extension = "png"
    content_type = "image/png"
    # Translators: status widget name
    verbose = gettext_lazy("PNG status badge")

    def render(self, request: HttpRequest, response: HttpResponse) -> None:
        label, value, color = self.get_badge_data(request)
        with rendering_lock():
            font_properties = get_font_properties(
                WIDGET_FONT, size=PNG_BADGE_FONT_SIZE, weight=400
            )
            label_width = ceil(measure_line(f"   {label}   ", font_properties)[0])
            value_width = ceil(measure_line(f"  {value}  ", font_properties)[0])
            width = label_width + value_width
            figure = create_figure(width, 20)
            draw_rectangle(figure, 0, 0, width, 20, color="#555", radius=3)
            draw_rectangle(
                figure,
                label_width,
                0,
                value_width,
                20,
                color=color,
                radius=3,
            )
            # Cover the rounded inner edge so only the outer corners are rounded.
            draw_rectangle(figure, label_width, 0, 4, 20, color=color)
            for text, center in (
                (label, label_width / 2),
                (value, label_width + value_width / 2),
            ):
                draw_text(
                    figure,
                    center,
                    PNG_BADGE_BASELINE + 1,
                    text,
                    font_properties=font_properties,
                    color=(0.01, 0.01, 0.01, 0.3),
                    horizontalalignment="center",
                    verticalalignment="baseline",
                )
                draw_text(
                    figure,
                    center,
                    PNG_BADGE_BASELINE,
                    text,
                    font_properties=font_properties,
                    color=(1, 1, 1),
                    horizontalalignment="center",
                    verticalalignment="baseline",
                )
            figure_to_png(figure, response)


@register_widget
class MultiLanguageWidget(SVGWidget):
    name = "multi"
    order = 81
    colors: tuple[str, ...] = ("auto", "red", "green", "blue")
    template_name = "svg/multi-language-badge.svg"
    verbose = pgettext_lazy("Status widget name", "Vertical language bar chart")

    COLOR_MAP: ClassVar[dict[str, str | None]] = {
        "red": "#fa3939",
        "green": "#3fed48",
        "blue": "#3f85ed",
        "auto": None,
    }

    def get_language_stats(self) -> list[BaseStats]:
        if isinstance(self.stats, (ProjectLanguageStats, TranslationStats)):
            return [self.stats]
        if isinstance(self.obj, ProjectLanguage):
            return [self.obj.stats]
        if isinstance(self.obj, Language):
            return [self.obj.stats]
        return self.stats.get_language_stats()

    def get_language_url(self, language: Language) -> str:
        if isinstance(self.obj, Component):
            return get_site_url(
                reverse(
                    "translate",
                    kwargs={"path": [*self.obj.get_url_path(), language.code]},
                )
            )
        if self.obj is None:
            return get_site_url(language.get_absolute_url())
        project_language = ProjectLanguage(self.obj, language)
        return get_site_url(project_language.get_absolute_url())

    def render(self, request: HttpRequest, response: HttpResponse) -> None:
        translations = []
        offset = 20
        color = self.COLOR_MAP[self.color]
        language_width = 190
        for stats in sort_unicode(self.get_language_stats(), lambda x: str(x.language)):
            # Skip empty translations
            if stats.translated == 0:
                continue
            language = stats.language
            percent = stats.translated_percent
            if self.color == "auto" or color is None:
                color = get_percent_color(percent)
            language_name = str(language)

            language_width = max(
                language_width,
                (render_size(text=language_name)[0].width + 10),
            )
            translations.append(
                (
                    # Language name
                    language_name,
                    # Translation percent
                    int(percent),
                    # Text y offset
                    offset,
                    # Bar y offset
                    offset - 6,
                    # Bar width
                    int(percent * 1.5),
                    # Bar color
                    color,
                    # Row URL
                    self.get_language_url(language),
                    # Top offset for horizontal
                    10 + int((100 - percent) * 1.5),
                )
            )
            offset += 15

        response.write(
            render_to_string(
                self.template_name,
                {
                    "height": len(translations) * 15 + 15,
                    "width": language_width + 210,
                    "language_offset": language_width,
                    "bar_offset": language_width + 10,
                    "text_offset": language_width + 170,
                    "translations": translations,
                    "site_url": get_site_url(),
                    "horizontal_height": language_width + 130,
                    "fonts_cdn_url": settings.FONTS_CDN_URL,
                },
            )
        )


@register_widget
class HorizontalMultiLanguageWidget(MultiLanguageWidget):
    name = "horizontal"
    order = 82
    template_name = "svg/multi-language-badge-horizontal.svg"
    verbose = pgettext_lazy("Status widget name", "Horizontal language bar chart")


@register_widget
class MatrixMultiLanguageWidget(MultiLanguageWidget):
    name = "matrix"
    order = 83
    template_name = "svg/multi-language-matrix.svg"
    verbose = pgettext_lazy("Status widget name", "Language progress matrix")

    min_cell_width = 100
    max_cell_width = 130
    max_width = 820
    cell_height = 20
    gap = 3
    margin = 6
    text_padding = 8
    percent_gap = 5
    text_size = 9

    def get_column_count(self, count: int, cell_width: int) -> int:
        max_columns = min(
            count,
            max(
                1,
                (self.max_width - self.margin * 2 + self.gap)
                // (cell_width + self.gap),
            ),
        )
        if count <= max_columns:
            return max(1, count)

        if count <= 12:
            desired = (count + 1) // 2
        elif count <= 40:
            desired = 5
        elif count <= 80:
            desired = 6
        else:
            desired = 8

        desired = min(max(1, desired), max_columns)

        def score(columns: int) -> tuple[int, int, int]:
            row_count, remainder = divmod(count, columns)
            if remainder:
                row_count += 1
            return (row_count, 1 if remainder == 1 else 0, abs(columns - desired))

        return min(range(1, max_columns + 1), key=score)

    def get_cell_width(self, language_names: list[str]) -> int:
        widest_language = max(
            (
                render_size(
                    language_name,
                    font=WIDGET_FONT,
                    weight=700,
                    size=self.text_size,
                )[0].width
                for language_name in language_names
            ),
            default=0,
        )
        percent_width = render_size("100%", font=WIDGET_FONT, size=self.text_size)[
            0
        ].width
        return min(
            self.max_cell_width,
            max(
                self.min_cell_width,
                widest_language + percent_width + self.percent_gap + self.text_padding,
            ),
        )

    def fit_text(self, text: str, max_width: int) -> str:
        if (
            render_size(text, font=WIDGET_FONT, weight=700, size=self.text_size)[
                0
            ].width
            <= max_width
        ):
            return text

        suffix = "..."
        low = 0
        high = len(text)
        while low < high:
            middle = (low + high + 1) // 2
            candidate = f"{text[:middle].rstrip()}{suffix}"
            if (
                render_size(
                    candidate,
                    font=WIDGET_FONT,
                    weight=700,
                    size=self.text_size,
                )[0].width
                <= max_width
            ):
                low = middle
            else:
                high = middle - 1
        if low == 0:
            return suffix
        return f"{text[:low].rstrip()}{suffix}"

    def render(self, request: HttpRequest, response: HttpResponse) -> None:
        cells: list[MatrixCellDict] = []
        color = self.COLOR_MAP[self.color]
        for stats in sort_unicode(self.get_language_stats(), lambda x: str(x.language)):
            # Skip empty translations
            if stats.translated == 0:
                continue
            language = stats.language
            percent = stats.translated_percent
            if self.color == "auto" or color is None:
                cell_color = get_percent_color(percent)
            else:
                cell_color = color

            cells.append(
                {
                    "name": str(language),
                    "percent": int(percent),
                    "progress_percent": min(max(percent, 0), 100),
                    "color": cell_color,
                    "url": self.get_language_url(language),
                }
            )

        cell_width = self.get_cell_width([cell["name"] for cell in cells])
        columns = self.get_column_count(len(cells), cell_width)
        percent_width = render_size("100%", font=WIDGET_FONT, size=self.text_size)[
            0
        ].width
        text_offset = self.text_padding // 2
        label_width = cell_width - self.text_padding - self.percent_gap - percent_width
        for index, cell in enumerate(cells):
            column = index % columns
            row = index // columns
            x = self.margin + column * (cell_width + self.gap)
            y = self.margin + row * (self.cell_height + self.gap)
            progress_percent = cell["progress_percent"]
            progress_width = round(cell_width * progress_percent / 100)
            if progress_percent:
                progress_width = max(1, progress_width)
            cell["x"] = x
            cell["y"] = y
            cell["label_x"] = x + text_offset
            cell["percent_x"] = x + cell_width - text_offset
            cell["text_y"] = y + 14
            cell["label"] = self.fit_text(cell["name"], label_width)
            cell["progress_width"] = progress_width

        rows = max(1, (len(cells) + columns - 1) // columns)
        width = columns * cell_width + (columns - 1) * self.gap + self.margin * 2
        height = rows * self.cell_height + (rows - 1) * self.gap + self.margin * 2

        response.write(
            render_to_string(
                self.template_name,
                {
                    "title": gettext("Translation status"),
                    "width": width,
                    "height": height,
                    "cell_width": cell_width,
                    "cell_height": self.cell_height,
                    "cells": cells,
                    "site_url": get_site_url(),
                },
            )
        )


@register_widget
class LanguageBadgeWidget(BaseSVGBadgeWidget):
    name = "language"
    order = 84
    # Translators: status widget name
    verbose = gettext_lazy("Language count badge")
    extra_parameters: ClassVar[list[ExtraParametersDict]] = [
        {
            "name": "threshold",
            "label": gettext("Threshold"),
            "type": "number",
            "default": 0,
            "min": 0,
            "max": 100,
            "step": 1,
        }
    ]

    def render(self, request: HttpRequest, response: HttpResponse) -> None:
        try:
            threshold = int(request.GET.get("threshold", 0))
        except ValueError as e:
            messages.error(
                request,
                gettext("Error in parameter %(field)s: %(error)s")
                % {
                    "field": "threshold",
                    "error": str(e),
                },
            )
            threshold = 0

        languages: list[BaseStats]
        if isinstance(self.stats, (ProjectLanguageStats, TranslationStats)):
            languages = [self.stats]
        elif isinstance(self.obj, (ProjectLanguage, Language)):
            languages = [self.obj.stats]
        else:
            languages = self.stats.get_language_stats()

        language_count = sum(
            1 for lang in languages if lang.translated_percent >= threshold
        )
        languages_text = ngettext("language", "languages", language_count)

        self.render_badge(response, languages_text, str(language_count), "#3fed48")
