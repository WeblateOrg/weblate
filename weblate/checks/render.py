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

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheckParametrized
from weblate.checks.parser import multi_value_flag
from weblate.fonts.utils import check_render_size

FONT_PARAMS = (
    ("font-family", "sans"),
    ("font-weight", None),
    ("font-size", 10),
    ("font-spacing", 0),
)

IMAGE = '<a href="{0}" class="thumbnail"><img class="img-responsive" src="{0}" /></a>'


class MaxSizeCheck(TargetCheckParametrized):
    """Check for maximum size of rendered text."""

    check_id = "max-size"
    name = _("Maximum size of translation")
    description = _("Translation rendered text should not exceed given size")
    default_disabled = True
    last_font = None
    always_display = True

    @property
    def param_type(self):
        return multi_value_flag(int, 1, 2)

    def get_params(self, unit):
        for name, default in FONT_PARAMS:
            if unit.all_flags.has_value(name):
                try:
                    yield unit.all_flags.get_value(name)
                except KeyError:
                    yield default
            else:
                yield default

    def load_font(self, project, language, name):
        try:
            group = project.fontgroup_set.get(name=name)
        except ObjectDoesNotExist:
            return "sans"
        try:
            override = group.fontoverride_set.get(language=language)
            return f"{override.font.family} {override.font.style}"
        except ObjectDoesNotExist:
            return f"{group.font.family} {group.font.style}"

    def check_target_params(self, sources, targets, unit, value):
        if len(value) == 2:
            width, lines = value
        else:
            width = value[0]
            lines = 1
        font_group, weight, size, spacing = self.get_params(unit)
        font = self.last_font = self.load_font(
            unit.translation.component.project, unit.translation.language, font_group
        )
        replace = self.get_replacement_function(unit)
        return any(
            (
                not check_render_size(
                    font,
                    weight,
                    size,
                    spacing,
                    replace(target),
                    width,
                    lines,
                    self.get_cache_key(unit, i),
                )
                for i, target in enumerate(targets)
            )
        )

    def get_description(self, check_obj):
        url = reverse(
            "render-check",
            kwargs={"check_id": self.check_id, "unit_id": check_obj.unit_id},
        )
        return mark_safe(
            "\n".join(
                IMAGE.format(f"{url}?pos={i}")
                for i in range(len(check_obj.unit.get_target_plurals()))
            )
        )

    def render(self, request, unit):
        try:
            pos = int(request.GET.get("pos", "0"))
        except ValueError:
            pos = 0
        key = self.get_cache_key(unit, pos)
        result = cache.get(key)
        if result is None:
            self.check_target_unit(
                unit.get_source_plurals(), unit.get_target_plurals(), unit
            )
            result = cache.get(key)
        if result is None:
            raise Http404("Invalid check")
        response = HttpResponse(content_type="image/png")
        response.write(result)
        return response
