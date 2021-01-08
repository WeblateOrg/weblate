#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
from typing import Optional

from django.core.cache import cache
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.cache import cache_control
from django.views.generic import TemplateView

from weblate.utils.hash import calculate_checksum

from .models import Setting


class CustomCSSView(TemplateView):
    template_name = "configuration/custom.css"
    cache_key = "css:custom"

    @classmethod
    def get_css(cls, request):
        # Request level caching
        if hasattr(request, "_weblate_custom_css"):
            return request._weblate_custom_css

        # Site level caching
        css = cache.get(cls.cache_key)
        if css is None:
            css = render_to_string(
                "configuration/custom.css",
                Setting.objects.get_settings_dict(Setting.CATEGORY_UI),
            ).strip()
            cache.set(cls.cache_key, css, 24 * 3600)
        request._weblate_custom_css = css
        return css

    @cache_control(max_age=7200)
    def get(self, request, *args, **kwargs):
        return HttpResponse(content_type="text/css", content=self.get_css(request))

    @classmethod
    def drop_cache(cls):
        cache.delete(cls.cache_key)

    @classmethod
    def get_hash(cls, request) -> Optional[str]:
        css = cls.get_css(request)
        if not css:
            return None
        return calculate_checksum(css)
