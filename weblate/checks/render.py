# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import TargetCheckParametrized
from weblate.checks.parser import multi_value_flag
from weblate.fonts.utils import check_render_size
from weblate.utils.hash import calculate_hash

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.trans.models import Unit

IMAGE = (
    '<a href="{0}" class="thumbnail img-check"><img class="img-fluid" src="{0}" /></a>'
)


class MaxSizeCheck(TargetCheckParametrized):
    """Check for maximum size of rendered text."""

    check_id = "max-size"
    name = gettext_lazy("Maximum size of translation")
    description = gettext_lazy("Rendered text should not exceed given size.")
    default_disabled = True
    last_font = None
    always_display = True
    source = True

    @property
    def param_type(self):
        return multi_value_flag(int, 1, 2)

    def get_params(self, unit: Unit) -> tuple[str, int | None, int, int]:
        all_flags = unit.all_flags
        return (
            all_flags.get_value_fallback("font-family", "sans"),
            all_flags.get_value_fallback("font-weight", None),
            all_flags.get_value_fallback("font-size", 10),
            all_flags.get_value_fallback("font-spacing", 0),
        )

    def load_font(self, project, language, name: str) -> str:
        try:
            group = project.fontgroup_set.get(name=name)
        except ObjectDoesNotExist:
            return "sans"
        try:
            override = group.fontoverride_set.get(language=language)
        except ObjectDoesNotExist:
            return f"{group.font.family} {group.font.style}"
        return f"{override.font.family} {override.font.style}"

    def get_render_cache_key(self, unit: Unit, pos: int, text: str) -> str:
        return f"{self.get_cache_key(unit, pos)}:{calculate_hash(text)}"

    def check_text_params(self, texts: list[str], unit: Unit, value) -> bool:
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
        failed = False
        for i, text in enumerate(texts):
            rendered_text = replace(text)
            if not check_render_size(
                text=rendered_text,
                font=font,
                weight=weight,
                size=size,
                spacing=spacing,
                width=width,
                lines=lines,
                cache_key=self.get_render_cache_key(unit, i, rendered_text),
            ):
                failed = True
        return failed

    def check_target_params(
        self, sources: list[str], targets: list[str], unit: Unit, value
    ):
        return self.check_text_params(targets, unit, value)

    def check_source_unit(self, sources: list[str], unit: Unit) -> bool:
        if unit.all_flags.has_value(self.enable_string):
            try:
                value = self.get_value(unit)
            except ValueError:
                return True
            return self.check_text_params(sources, unit, value)
        return False

    def get_render_plurals(self, unit: Unit) -> list[str]:
        if unit.is_source:
            return unit.get_source_plurals()
        return unit.get_target_plurals()

    def get_description(self, check_obj):
        url = reverse(
            "render-check",
            kwargs={"check_id": self.check_id, "unit_id": check_obj.unit_id},
        )
        images = format_html_join(
            "\n",
            IMAGE,
            (
                (f"{url}?pos={i}",)
                for i in range(len(self.get_render_plurals(check_obj.unit)))
            ),
        )
        if not check_obj.id:
            return format_html(
                "{}{}",
                gettext(
                    "It fits into given boundaries. The rendering is shown for your convenience."
                ),
                images,
            )
        return images

    def render(self, request: AuthenticatedHttpRequest, unit: Unit):
        try:
            pos = int(request.GET.get("pos", "0"))
        except ValueError:
            pos = 0
        texts = self.get_render_plurals(unit)
        try:
            text = texts[pos]
        except IndexError:
            msg = "Invalid check"
            raise Http404(msg) from None
        key = self.get_render_cache_key(
            unit, pos, self.get_replacement_function(unit)(text)
        )
        result = cache.get(key)
        if result is None:
            if unit.is_source:
                self.check_source_unit(unit.get_source_plurals(), unit)
            else:
                self.check_target_unit(
                    unit.get_source_plurals(), unit.get_target_plurals(), unit
                )
            result = cache.get(key)
        if result is None:
            msg = "Invalid check"
            raise Http404(msg)
        response = HttpResponse(content_type="image/png")
        response.write(result)
        return response
