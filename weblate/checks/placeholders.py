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


@staticmethod
def parse_placeholders(val):
    return val.split(":")


@staticmethod
def parse_regex(val):
    return re.compile(val)


class PlaceholderCheck(TargetCheckParametrized):
    check_id = "placeholders"
    default_disabled = True
    name = _("Placeholders")
    description = _("Translation is missing some placeholders")
    severity = "danger"
    param_type = parse_placeholders

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


class RegexCheck(TargetCheckParametrized):
    check_id = "regex"
    default_disabled = True
    name = _("Regular expression")
    description = _("Translation does not match regular expression:")
    severity = "danger"
    param_type = parse_regex

    def check_target_params(self, sources, targets, unit, value):
        return any(not value.findall(target) for target in targets)

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
        regex = self.get_value(unit)
        return mark_safe(
            "{} <code>{}</code>".format(escape(self.description), escape(regex.pattern))
        )
