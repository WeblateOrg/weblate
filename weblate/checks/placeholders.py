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


import re

from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheckParametrized
from weblate.checks.parser import multi_value_flag, single_value_flag


def parse_regex(val):
    return re.compile(val)


class PlaceholderCheck(TargetCheckParametrized):
    check_id = "placeholders"
    default_disabled = True
    name = _("Placeholders")
    description = _("Translation is missing some placeholders:")

    @property
    def param_type(self):
        return multi_value_flag(str)

    def check_target_params(self, sources, targets, unit, value):
        return any(any(param not in target for param in value) for target in targets)

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return []
        ret = []

        regexp = "|".join(re.escape(param) for param in self.get_value(unit))

        for match in re.finditer(regexp, source):
            ret.append((match.start(), match.end(), match.group()))
        return ret

    def get_description(self, check_obj):
        unit = check_obj.unit
        if not self.has_value(unit):
            return super().get_description(check_obj)
        targets = unit.get_target_plurals()
        missing = [
            param
            for param in self.get_value(unit)
            if any(param not in target for target in targets)
        ]
        return mark_safe(
            "{} {}".format(escape(self.description), escape(", ".join(missing)))
        )


class RegexCheck(TargetCheckParametrized):
    check_id = "regex"
    default_disabled = True
    name = _("Regular expression")
    description = _("Translation does not match regular expression:")

    @property
    def param_type(self):
        return single_value_flag(parse_regex)

    def check_target_params(self, sources, targets, unit, value):
        return any(not value.findall(target) for target in targets)

    def should_skip(self, unit):
        if super().should_skip(unit):
            return True
        return bool(self.get_value(unit))

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return []
        ret = []

        regex = self.get_value(unit)

        for match in regex.finditer(source):
            ret.append((match.start(), match.end(), match.group()))
        return ret

    def get_description(self, check_obj):
        unit = check_obj.unit
        if not self.has_value(unit):
            return super().get_description(check_obj)
        regex = self.get_value(unit)
        return mark_safe(
            "{} <code>{}</code>".format(escape(self.description), escape(regex.pattern))
        )
