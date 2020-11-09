#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django.views.generic import TemplateView

from .models import Setting


@method_decorator(cache_control(max_age=3600), name="dispatch")
class CustomCSSView(TemplateView):
    template_name = "configuration/custom.css"
    content_type = "text/css"
    cache_key = "css:custom"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["settings"] = Setting.objects.get_settings_dict(Setting.CATEGORY_UI)
        return context

    def get(self, request, *args, **kwargs):
        response = cache.get(self.cache_key)
        if response is None:
            response = super().get(request, *args, **kwargs)
            response.add_post_render_callback(
                lambda r: cache.set(self.cache_key, r, 3600)
            )
        return response

    @classmethod
    def drop_cache(cls):
        cache.delete(cls.cache_key)
