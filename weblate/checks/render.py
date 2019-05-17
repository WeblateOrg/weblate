# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _

from weblate.checks.base import TargetCheckParametrized
from weblate.fonts.utils import FONT_WEIGHTS, check_render_size

FONT_PARAMS = (
    ("font-family", "sans"),
    ("font-weight", FONT_WEIGHTS["normal"]),
    ("font-size", 10),
    ("font-spacing", 0),
)


@staticmethod
def parse_size(val):
    if ":" in val:
        width, lines = val.split(":")
        return int(width), int(lines)
    return int(val)


class MaxSizeCheck(TargetCheckParametrized):
    """Check for maximum size of rendered text."""

    check_id = "max-size"
    name = _("Maximum size of translation")
    description = _("Translation rendered text should not exceed given size")
    severity = "danger"
    default_disabled = True
    param_type = parse_size
    last_font = None

    def get_params(self, unit):
        for name, default in FONT_PARAMS:
            if unit.all_flags.has_value(name):
                yield unit.all_flags.get_value(name)
            else:
                yield default

    def load_font(self, project, language, name):
        try:
            group = project.fontgroup_set.get(name=name)
        except ObjectDoesNotExist:
            return "sans"
        try:
            override = group.fontoverride_set.get(language=language)
            return override.font.family
        except ObjectDoesNotExist:
            return group.font.family

    def check_target_params(self, sources, targets, unit, value):
        if isinstance(value, tuple):
            width, lines = value
        else:
            width = value
            lines = 1
        font_group, weight, size, spacing = self.get_params(unit)
        font = self.last_font = self.load_font(
            unit.translation.component.project, unit.translation.language, font_group
        )
        return any(
            (
                not check_render_size(font, weight, size, spacing, target, width, lines)
                for target in targets
            )
        )
