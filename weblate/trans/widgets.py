# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os.path

import cairo
import gi
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import (
    get_language,
    gettext,
    gettext_lazy,
    npgettext,
    pgettext,
    pgettext_lazy,
)

from weblate.fonts.utils import configure_fontconfig, render_size
from weblate.trans.models import Project
from weblate.trans.templatetags.translations import number_format
from weblate.trans.util import sort_unicode
from weblate.utils.site import get_site_url
from weblate.utils.stats import GlobalStats
from weblate.utils.views import get_percent_color

gi.require_version("PangoCairo", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

COLOR_DATA = {
    "grey": (0, 0, 0),
    "white": (0, 0, 0),
    "black": (255, 255, 255),
    "graph": (255, 255, 255),
}

WIDGETS = {}
WIDGET_FONT = "Source Sans 3"


def register_widget(widget):
    """Register widget in dictionary."""
    WIDGETS[widget.name] = widget
    return widget


class Widget:
    """Generic widget class."""

    name = ""
    verbose = ""
    colors: tuple[str, ...] = ()
    extension = "png"
    content_type = "image/png"
    order = 100

    def __init__(self, obj, color=None, lang=None):
        """Create Widget object."""
        # Get object and related params
        self.obj = obj
        self.color = self.get_color_name(color)
        self.lang = lang

    def get_color_name(self, color):
        """Return color name based on allowed ones."""
        if color not in self.colors:
            return self.colors[0]
        return color


class ContentWidget(Widget):
    """Generic content widget class."""

    def __init__(self, obj, color=None, lang=None):
        """Create Widget object."""
        super().__init__(obj, color, lang)
        # Get translation status
        stats = obj.stats.get_single_language_stats(lang) if lang else obj.stats
        self.percent = stats.translated_percent

    def get_percent_text(self):
        return pgettext("Translated percents", "%(percent)s%%") % {
            "percent": int(self.percent)
        }


class BitmapWidget(ContentWidget):
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

    def __init__(self, obj, color=None, lang=None):
        """Create Widget object."""
        super().__init__(obj, color, lang)
        # Get object and related params
        self.total = obj.stats.source_strings
        self.languages = obj.stats.languages
        self.params = self.get_text_params()

        # Set rendering variables
        self.draw = None
        self.width = 0

    def get_text_params(self):
        """Create dictionary used for text formatting."""
        return {
            "name": self.obj.name,
            "count": self.total,
            "languages": self.languages,
            "percent": self.percent,
        }

    def get_filename(self):
        """Return widgets filename."""
        return os.path.join(
            settings.STATIC_ROOT,
            "widget-images",
            f"{self.name}-{self.color}.png",
        )

    def get_columns(self):
        raise NotImplementedError

    def get_column_width(self, surface, columns):
        return surface.get_width() // len(columns)

    def get_column_fonts(self):
        return [
            Pango.FontDescription(f"{WIDGET_FONT} {self.font_size * 1.5}"),
            Pango.FontDescription(f"{WIDGET_FONT} {self.font_size}"),
        ]

    def render_additional(self, ctx):
        return

    def render(self, response):
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


class SVGWidget(ContentWidget):
    """Base class for SVG rendering widgets."""

    extension = "svg"
    content_type = "image/svg+xml; charset=utf-8"
    template_name = ""

    def render(self, response):
        """Rendering method to be implemented."""
        raise NotImplementedError


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

    def get_column_width(self, surface, columns):
        return 230

    def get_column_fonts(self):
        return [
            Pango.FontDescription(f"{WIDGET_FONT} {42}"),
            Pango.FontDescription(f"{WIDGET_FONT} {18}"),
        ]

    def get_name(self) -> str:
        return str(self.obj)

    def get_title(self, name: str, suffix: str = "") -> str:
        # Translators: Text on OpenGraph image
        if isinstance(self.obj, Project):
            template = gettext("Project {}")
        else:
            template = gettext("Component {}")

        return format_html(template, format_html("<b>{}</b>{}", name, suffix))

    def render_additional(self, ctx):
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


class SiteOpenGraphWidget(OpenGraphWidget):
    def __init__(self, obj=None, color=None, lang=None):
        super().__init__(GlobalStats())

    def get_name(self) -> str:
        return settings.SITE_TITLE

    def get_title(self, name: str, suffix: str = "") -> str:
        return format_html("<b>{}</b>{}", name, suffix)

    def get_text_params(self):
        return {}


@register_widget
class SVGBadgeWidget(SVGWidget):
    name = "svg"
    colors: tuple[str, ...] = ("badge",)
    order = 80
    template_name = "svg/badge.svg"
    verbose = gettext_lazy("Status badge")

    def render(self, response):
        translated_text = gettext("translated")
        translated_width = render_size(
            "Kurinto Sans", Pango.Weight.NORMAL, 11, 0, f"   {translated_text}   "
        )[0].width

        percent_text = self.get_percent_text()
        percent_width = render_size(
            "Kurinto Sans", Pango.Weight.NORMAL, 11, 0, f"  {percent_text}  "
        )[0].width

        if self.percent >= 90:
            color = "#4c1"
        elif self.percent >= 75:
            color = "#dfb317"
        else:
            color = "#e05d44"

        response.write(
            render_to_string(
                self.template_name,
                {
                    "translated_text": translated_text,
                    "percent_text": percent_text,
                    "translated_width": translated_width,
                    "percent_width": percent_width,
                    "width": translated_width + percent_width,
                    "color": color,
                    "translated_offset": translated_width // 2,
                    "percent_offset": translated_width + percent_width // 2,
                    "lang": get_language(),
                    "fonts_cdn_url": settings.FONTS_CDN_URL,
                },
            )
        )


@register_widget
class MultiLanguageWidget(SVGWidget):
    name = "multi"
    order = 81
    colors: tuple[str, ...] = ("auto", "red", "green", "blue")
    template_name = "svg/multi-language-badge.svg"
    verbose = pgettext_lazy("Status widget name", "Vertical language bar chart")

    COLOR_MAP = {"red": "#fa3939", "green": "#3fed48", "blue": "#3f85ed", "auto": None}

    def render(self, response):
        translations = []
        offset = 20
        color = self.COLOR_MAP[self.color]
        language_width = 190
        languages = self.obj.stats.get_language_stats()
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
                (
                    render_size(
                        "Kurinto Sans", Pango.Weight.NORMAL, 11, 0, language_name
                    )[0].width
                    + 10
                ),
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
                    get_site_url(
                        reverse(
                            "project-language",
                            kwargs={"lang": language.code, "project": self.obj.slug},
                        )
                    ),
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
