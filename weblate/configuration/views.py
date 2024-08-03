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

from .models import Setting

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@method_decorator(cache_control(max_age=7200), name="get")
class CustomCSSView(TemplateView):
    template_name = "configuration/custom.css"
    cache_key = "css:custom"

    @classmethod
    def get_css(cls, request: AuthenticatedHttpRequest):
        # Request level caching
        if hasattr(request, "weblate_custom_css"):
            return request.weblate_custom_css

        # Site level caching
        css = cache.get(cls.cache_key)
        if css is None:
            css = render_to_string(
                "configuration/custom.css",
                Setting.objects.get_settings_dict(Setting.CATEGORY_UI),
            ).strip()
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
