# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os.path
from io import StringIO
from typing import TYPE_CHECKING

import cairo
import gi
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.translation import (
    get_language,
    gettext,
    gettext_lazy,
    ngettext,
    npgettext,
    pgettext,
    pgettext_lazy,
)

from weblate.fonts.utils import configure_fontconfig, render_size
from weblate.lang.models import Language
from weblate.trans.models import Project
from weblate.trans.templatetags.translations import number_format
from weblate.trans.util import sort_unicode, translation_percent
from weblate.utils.icons import find_static_file
from weblate.utils.site import get_site_url
from weblate.utils.stats import (
    BaseStats,
    GlobalStats,
    ProjectLanguage,
    ProjectLanguageStats,
    TranslationStats,
    get_non_glossary_stats,
)
from weblate.utils.views import get_percent_color

if TYPE_CHECKING:
    from django.http import HttpResponse
    from django_stubs_ext import StrOrPromise

gi.require_version("PangoCairo", "1.0")
gi.require_version("Pango", "1.0")
gi.require_version("Rsvg", "2.0")

from gi.repository import Pango, PangoCairo, Rsvg  # noqa: E402

COLOR_DATA = {
    "grey": (0, 0, 0),
    "white": (0, 0, 0),
    "black": (255, 255, 255),
    "graph": (255, 255, 255),
}

WIDGETS: dict[str, type[Widget]] = {}
WIDGET_FONT = "Source Sans 3"


def register_widget(widget):
    """Register widget in dictionary."""
    WIDGETS[widget.name] = widget
    return widget


class Widget:
    """Generic widget class."""

    name = ""
    verbose: StrOrPromise = ""
    colors: tuple[str, ...] = ()
    extension = "png"
    content_type = "image/png"
    order = 100

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


class BitmapWidget(Widget):
    """Base class for bitmap rendering widgets."""

    colors: tuple[str, ...] = ("grey", "white", "black")
    extension = "png"
    content_type = "image/png"
    order = 100
    head_template = '<span letter_spacing="-500"><b>{}</b></span>'
    foot_template = '<span letter_spacing="1000">{}</span>'
    font_size = 10
    line_spacing = 1.0
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

    def get_column_width(self, surface, columns):
        return surface.get_width() // len(columns)

    def get_column_fonts(self):
        return [
            Pango.FontDescription(f"{WIDGET_FONT} {self.font_size * 1.5}"),
            Pango.FontDescription(f"{WIDGET_FONT} {self.font_size}"),
        ]

    def render_additional(self, ctx) -> None:
        return

    def render(self, response) -> None:
        """Render widget."""
        configure_fontconfig()
        surface = cairo.ImageSurface.create_from_png(self.get_filename())
        height = surface.get_height()
        ctx = cairo.Context(surface)

        columns = self.get_columns()
        column_width = self.get_column_width(surface, columns)

        fonts = self.get_column_fonts()

        for i, column in enumerate(columns):
            offset = self.offset
            for row, text in enumerate(column):
                layout = PangoCairo.create_layout(ctx)
                layout.set_font_description(fonts[row])

                # Set color and position
                ctx.move_to(self.column_offset + column_width * i, offset)
                ctx.set_source_rgb(*COLOR_DATA[self.color])

                # Add text
                layout.set_markup(text)
                layout.set_alignment(Pango.Alignment.CENTER)
                layout.set_width(column_width * Pango.SCALE)

                offset += layout.get_pixel_size().height * self.line_spacing

                # Render to cairo context
                PangoCairo.show_layout(ctx, layout)

            # Render column separators
            if self.lines and i > 0:
                ctx.new_path()
                ctx.set_source_rgb(*COLOR_DATA[self.color])
                ctx.set_line_width(0.5)
                ctx.move_to(column_width * i, self.offset)
                ctx.line_to(column_width * i, height - self.offset)
                ctx.stroke()

        self.render_additional(ctx)

        surface.write_to_png(response)


class SVGWidget(Widget):
    """Base class for SVG rendering widgets."""

    extension = "svg"
    content_type = "image/svg+xml; charset=utf-8"
    template_name = ""

    def render(self, response) -> None:
        raise NotImplementedError


class PNGWidget(SVGWidget):
    extension = "png"
    content_type = "image/png"

    def render(self, response) -> None:
        with StringIO() as output:
            super().render(output)
            svgdata = output.getvalue()

        handle = Rsvg.Handle.new_from_data(svgdata.encode())
        if hasattr(handle, "get_intrinsic_size_in_pixels"):
            # librsvg 2.52 and newer
            out_dimensions = handle.get_intrinsic_size_in_pixels()
            width = int(out_dimensions.out_width)
            height = int(out_dimensions.out_height)
        else:
            dimensions = handle.get_dimensions()
            width = int(dimensions.width)
            height = int(dimensions.height)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        context = cairo.Context(surface)
        if hasattr(Rsvg, "Rectangle"):
            # librsvg 2.46 and newer
            viewport = Rsvg.Rectangle()
            viewport.x = 0
            viewport.y = 0
            viewport.width = width
            viewport.height = height
            handle.render_document(context, viewport)
        else:
            # librsvg before 2.46, this method is now deprecated
            handle.render_cairo(context)
        surface.write_to_png(response)


@register_widget
class NormalWidget(BitmapWidget):
    name = "287x66"
    order = 110
    offset = 10
    verbose = gettext_lazy("Big status badge")

    def get_columns(self):
        return [
            [
                format_html(self.head_template, number_format(self.total)),
                format_html(
                    self.foot_template,
                    npgettext(
                        "Label on engage page", "String", "Strings", self.total
                    ).upper(),
                ),
            ],
            [
                format_html(self.head_template, number_format(self.languages)),
                format_html(
                    self.foot_template,
                    npgettext(
                        "Label on engage page", "Language", "Languages", self.languages
                    ).upper(),
                ),
            ],
            [
                format_html(self.head_template, self.get_percent_text()),
                format_html(self.foot_template, gettext("Translated").upper()),
            ],
        ]


@register_widget
class SmallWidget(BitmapWidget):
    name = "88x31"
    order = 111
    font_size = 7
    line_spacing = 0.8
    offset = -1
    verbose = gettext_lazy("Small status badge")

    def get_columns(self):
        return [
            [
                format_html(self.head_template, self.get_percent_text()),
                format_html(self.foot_template, gettext("Translated").upper()),
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
    head_template = '<span letter_spacing="-1000">{}</span>'
    foot_template = '<span letter_spacing="2000">{}</span>'
    verbose = pgettext_lazy("Status widget name", "Panel")

    def get_column_width(self, surface, columns) -> int:
        return 230

    def get_column_fonts(self):
        return [
            Pango.FontDescription(f"{WIDGET_FONT} {42}"),
            Pango.FontDescription(f"{WIDGET_FONT} {18}"),
        ]

    def get_name(self) -> str:
        if self.obj is None:
            return settings.SITE_TITLE
        return str(self.obj)

    def get_title(self, name: str, suffix: str = "") -> str:
        if self.obj is None:
            template = "{}"
        elif isinstance(self.obj, Project):
            # Translators: Text on OpenGraph image
            template = gettext("Project {}")
        else:
            # Translators: Text on OpenGraph image
            template = gettext("Component {}")

        return format_html(template, format_html("<b>{}</b>{}", name, suffix))

    def render_additional(self, ctx) -> None:
        ctx.move_to(280, 170)
        layout = PangoCairo.create_layout(ctx)
        layout.set_font_description(Pango.FontDescription(f"{WIDGET_FONT} {52}"))
        name = self.get_name()
        layout.set_markup(self.get_title(name))

        max_width = 1200 - 280
        while layout.get_size().width / Pango.SCALE > max_width:
            if " " in name:
                name = name.rsplit(" ", 1)[0]
            elif "-" in name:
                name = name.rsplit("-", 1)[0]
            elif "_" in name:
                name = name.rsplit("_", 1)[0]
            else:
                name = name[:-1]
            layout.set_markup(self.get_title(f"{name}", "…"))
            if not name:
                break

        PangoCairo.show_layout(ctx, layout)


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
    verbose = gettext_lazy("SVG status badge")

    def render(self, response: HttpResponse) -> None:
        translated_text = gettext("translated")
        percent_text = self.get_percent_text()
        if self.percent >= 90:
            color = "#4c1"
        elif self.percent >= 75:
            color = "#dfb317"
        else:
            color = "#e05d44"
        self.render_badge(response, translated_text, percent_text, color)


@register_widget
class PNGBadgeWidget(PNGWidget, SVGBadgeWidget):
    name = "status"
    verbose = gettext_lazy("PNG status badge")


@register_widget
class MultiLanguageWidget(SVGWidget):
    name = "multi"
    order = 81
    colors: tuple[str, ...] = ("auto", "red", "green", "blue")
    template_name = "svg/multi-language-badge.svg"
    verbose = pgettext_lazy("Status widget name", "Vertical language bar chart")

    COLOR_MAP = {"red": "#fa3939", "green": "#3fed48", "blue": "#3f85ed", "auto": None}

    def render(self, response) -> None:
        translations = []
        offset = 20
        color = self.COLOR_MAP[self.color]
        language_width = 190
        languages: list[BaseStats | ProjectLanguage]
        if isinstance(self.stats, ProjectLanguageStats | TranslationStats):
            languages = [self.stats]
        elif isinstance(self.obj, ProjectLanguage):
            languages = [self.obj]
        elif isinstance(self.obj, Language):
            languages = [self.obj.stats]
        else:
            languages = self.stats.get_language_stats()
        for stats in sort_unicode(languages, lambda x: str(x.language)):
            # Skip empty translations
            if stats.translated == 0:
                continue
            language = stats.language
            percent = stats.translated_percent
            if self.color == "auto":
                color = get_percent_color(percent)
            language_name = str(language)

            language_width = max(
                language_width,
                (render_size(text=language_name)[0].width + 10),
            )
            if self.obj is None:
                project_language = language
            else:
                project_language = ProjectLanguage(self.obj, language)
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
                    get_site_url(project_language.get_absolute_url()),
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
class LanguageBadgeWidget(BaseSVGBadgeWidget):
    name = "language"
    order = 83
    verbose = gettext_lazy("Language count badge")

    def render(self, response: HttpResponse) -> None:
        languages: list[BaseStats | ProjectLanguage]
        if isinstance(self.stats, ProjectLanguageStats | TranslationStats):
            languages = [self.stats]
        elif isinstance(self.obj, ProjectLanguage):
            languages = [self.obj]
        elif isinstance(self.obj, Language):
            languages = [self.obj.stats]
        else:
            languages = self.stats.get_language_stats()

        language_count = sum(1 for _ in languages)
        languages_text = ngettext("language", "languages", language_count)

        self.render_badge(response, languages_text, str(language_count), "#3fed48")
