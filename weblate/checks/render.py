# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import TargetCheckParametrized
from weblate.checks.parser import multi_value_flag
from weblate.fonts.limits import (
    MAX_RENDER_CHARACTERS,
    RenderLimitError,
    render_limit_message,
    validate_render_params,
)
from weblate.fonts.utils import check_render_size
from weblate.utils.hash import calculate_hash

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.checks.models import Check
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

    def load_font(self, project, language, name: str) -> tuple[str, tuple[str, ...]]:
        try:
            group = project.fontgroup_set.get(name=name)
        except ObjectDoesNotExist:
            return "sans", ()
        try:
            override = group.fontoverride_set.get(language=language)
        except ObjectDoesNotExist:
            selected_font = group.font
        else:
            selected_font = override.font
        sibling_paths = tuple(
            font.font.path
            for font in project.font_set.filter(family=selected_font.family).exclude(
                pk=selected_font.pk
            )
        )
        return selected_font.font.path, sibling_paths

    def get_render_cache_key(self, unit: Unit, pos: int, text: str) -> str:
        return f"{self.get_cache_key(unit, pos)}:{calculate_hash(text)}"

    def prepare_render_text(self, unit: Unit, text: str, value: tuple[int, ...]) -> str:
        width = value[0]
        lines = value[1] if len(value) == 2 else 1
        _font, _weight, size, spacing = self.get_params(unit)
        validate_render_params(
            text, width=width, lines=lines, size=size, spacing=spacing
        )
        try:
            text = self.get_replacement_function(
                unit, max_length=MAX_RENDER_CHARACTERS
            )(text)
        except ValueError as error:
            raise RenderLimitError from error
        validate_render_params(
            text, width=width, lines=lines, size=size, spacing=spacing
        )
        return text

    def check_text_params(self, texts: list[str], unit: Unit, value) -> bool:
        try:
            texts = [self.prepare_render_text(unit, text, value) for text in texts]
        except RenderLimitError:
            return True
        if len(value) == 2:
            width, lines = value
        else:
            width = value[0]
            lines = 1
        font_group, weight, size, spacing = self.get_params(unit)
        font, font_siblings = self.load_font(
            unit.translation.component.project, unit.translation.language, font_group
        )
        self.last_font = font
        failed = False
        for i, text in enumerate(texts):
            cache_key = self.get_render_cache_key(unit, i, text)
            try:
                fits = check_render_size(
                    text=text,
                    font=font,
                    font_siblings=font_siblings,
                    weight=weight,
                    size=size,
                    spacing=spacing,
                    width=width,
                    lines=lines,
                    cache_key=cache_key,
                )
            except RenderLimitError:
                cache.set(f"{cache_key}:limit", True, timeout=4200)
                return True
            cache.set(f"{cache_key}:limit", False, timeout=4200)
            if not fits:
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
            return unit.get_effective_source_plurals()
        return unit.get_target_plurals()

    def exceeds_render_budget(
        self, unit: Unit, text: str, value: tuple[int, ...]
    ) -> bool:
        """Recover the limit result after cache eviction without drawing a preview."""
        group, weight, size, spacing = self.get_params(unit)
        font, siblings = self.load_font(
            unit.translation.component.project, unit.translation.language, group
        )
        try:
            check_render_size(
                text=text,
                font=font,
                font_siblings=siblings,
                weight=weight,
                size=size,
                spacing=spacing,
                width=value[0],
                lines=value[1] if len(value) == 2 else 1,
            )
        except RenderLimitError:
            return True
        return False

    def get_description(self, check_obj: Check) -> str:
        unit = check_obj.unit
        if unit.all_flags.has_value(self.enable_string):
            try:
                value = self.get_value(check_obj.unit)
            except ValueError:
                return str(super().get_description(check_obj))
            for pos, text in enumerate(self.get_render_plurals(unit)):
                try:
                    expanded = self.get_replacement_function(
                        unit, max_length=MAX_RENDER_CHARACTERS
                    )(text)
                except ValueError:
                    return render_limit_message()
                cache_key = self.get_render_cache_key(unit, pos, expanded)
                if cache.get(cache_key) is not None:
                    continue
                try:
                    expanded = self.prepare_render_text(unit, text, value)
                except RenderLimitError:
                    return render_limit_message()
                limit_key = f"{cache_key}:limit"
                exceeded = cache.get(limit_key)
                if exceeded is None:
                    exceeded = self.exceeds_render_budget(unit, expanded, value)
                    cache.set(limit_key, exceeded, timeout=4200)
                if exceeded:
                    return render_limit_message()
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

    def render(self, request: AuthenticatedHttpRequest, unit: Unit) -> HttpResponse:
        try:
            return self.render_preview(request, unit)
        except RenderLimitError:
            return HttpResponseBadRequest(render_limit_message())

    def render_preview(
        self, request: AuthenticatedHttpRequest, unit: Unit
    ) -> HttpResponse:
        try:
            pos = int(request.GET.get("pos", "0"))
        except ValueError:
            pos = 0
        texts = self.get_render_plurals(unit)
        if pos < 0:
            msg = "Invalid check"
            raise Http404(msg)
        try:
            text = texts[pos]
        except IndexError:
            msg = "Invalid check"
            raise Http404(msg) from None
        try:
            rendered_text = self.get_replacement_function(
                unit, max_length=MAX_RENDER_CHARACTERS
            )(text)
        except ValueError as error:
            raise RenderLimitError from error
        key = self.get_render_cache_key(unit, pos, rendered_text)
        result = cache.get(key)
        if result is None:
            try:
                value = self.get_value(unit)
            except (KeyError, ValueError) as error:
                msg = "Invalid rendering configuration for this string."
                raise Http404(msg) from error
            self.prepare_render_text(unit, text, value)
            if unit.is_source:
                self.check_source_unit(unit.get_effective_source_plurals(), unit)
            else:
                self.check_target_unit(
                    unit.get_effective_source_plurals(), unit.get_target_plurals(), unit
                )
            result = cache.get(key)
        if result is None:
            raise RenderLimitError
        response = HttpResponse(content_type="image/png")
        response.write(result)
        return response
