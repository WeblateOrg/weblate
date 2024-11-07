# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.cache import cache
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django.views.generic import TemplateView

from weblate.utils.hash import calculate_checksum

from .models import Setting, SettingCategory

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@method_decorator(cache_control(max_age=7200), name="get")
class CustomCSSView(TemplateView):
    template_name = "configuration/custom.css"
    cache_key = "css:custom"

    @classmethod
    def split_colors(cls, hex_color_string):
        if hex_color_string:
            colors = hex_color_string.split(",")
            if len(colors) == 1:
                return [colors[0], colors[0]]
            if len(colors) == 2:
                return colors
            return [None, None]
        return [None, None]

    @classmethod
    def get_css(cls, request: AuthenticatedHttpRequest):
        # Request level caching
        if hasattr(request, "weblate_custom_css"):
            return request.weblate_custom_css

        # Site level caching
        css = cache.get(cls.cache_key)
        if css is None:
            settings = Setting.objects.get_settings_dict(SettingCategory.UI)
            split_colors = cls.split_colors
            # fmt: off
            custom_theme_settings = {
                "header_color_light": split_colors(settings.get("header_color"))[0],
                "header_color_dark": split_colors(settings.get("header_color"))[1],
                "header_text_color_light": split_colors(settings.get("header_text_color"))[0],
                "header_text_color_dark": split_colors(settings.get("header_text_color"))[1],
                "navi_color_light": split_colors(settings.get("navi_color"))[0],
                "navi_color_dark": split_colors(settings.get("navi_color"))[1],
                "navi_text_color_light": split_colors(settings.get("navi_text_color"))[0],
                "navi_text_color_dark": split_colors(settings.get("navi_text_color"))[1],
                "focus_color_light": split_colors(settings.get("focus_color"))[0],
                "focus_color_dark": split_colors(settings.get("focus_color"))[1],
                "hover_color_light": split_colors(settings.get("hover_color"))[0],
                "hover_color_dark": split_colors(settings.get("hover_color"))[1],
                "hide_footer": settings.get("hide_footer"),
                "page_font": settings.get("page_font"),
                "brand_font": settings.get("brand_font"),
                "enforce_hamburger": settings.get("enforce_hamburger"),
            }
            # fmt: on

            css = render_to_string(cls.template_name, custom_theme_settings).strip()
            cache.set(cls.cache_key, css, 24 * 3600)
        request.weblate_custom_css = css
        return css

    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        return HttpResponse(content_type="text/css", content=self.get_css(request))

    @classmethod
    def drop_cache(cls) -> None:
        cache.delete(cls.cache_key)

    @classmethod
    def get_hash(cls, request: AuthenticatedHttpRequest) -> str | None:
        css = cls.get_css(request)
        if not css:
            return None
        return calculate_checksum(css)
