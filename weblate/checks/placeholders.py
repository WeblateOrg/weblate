#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

from django.utils.html import escape, format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheckParametrized
from weblate.checks.parser import multi_value_flag, single_value_flag


def parse_regex(val):
    if isinstance(val, str):
        return re.compile(val)
    return val


class PlaceholderCheck(TargetCheckParametrized):
    check_id = "placeholders"
    default_disabled = True
    name = _("Placeholders")
    description = _("Translation is missing some placeholders")

    @property
    def param_type(self):
        return multi_value_flag(lambda x: x)

    def get_value(self, unit):
        return re.compile(
            "|".join(
                re.escape(param) if isinstance(param, str) else param.pattern
                for param in super().get_value(unit)
            ),
            re.IGNORECASE if "case-insensitive" in unit.all_flags else 0,
        )

    @staticmethod
    def get_matches(value, text: str):
        for match in value.finditer(text):
            yield match.group()

    def diff_case_sensitive(self, expected, found):
        return expected - found, found - expected

    def diff_case_insensitive(self, expected, found):
        expected_fold = {v.casefold(): v for v in expected}
        found_fold = {v.casefold(): v for v in found}

        expected_set = set(expected_fold)
        found_set = set(found_fold)

        return (
            {expected_fold[v] for v in expected_set - found_set},
            {found_fold[v] for v in found_set - expected_set},
        )

    def check_target_params(self, sources, targets, unit, value):
        expected = set(self.get_matches(value, unit.source_string))

        if "case-insensitive" in unit.all_flags:
            diff_func = self.diff_case_insensitive
        else:
            diff_func = self.diff_case_sensitive

        missing = set()
        extra = set()

        for target in targets:
            found = set(self.get_matches(value, target))
            diff = diff_func(expected, found)
            missing.update(diff[0])
            extra.update(diff[1])

        if missing or extra:
            return {"missing": missing, "extra": extra}
        return False

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return

        regexp = self.get_value(unit)

        for match in regexp.finditer(source):
            yield (match.start(), match.end(), match.group())

    def get_description(self, check_obj):
        unit = check_obj.unit
        result = self.check_target_unit(
            unit.get_source_plurals(), unit.get_target_plurals(), unit
        )
        if not result:
            return super().get_description(check_obj)

        errors = []
        if result["missing"]:
            errors.append(self.get_missing_text(result["missing"]))
        if result["extra"]:
            errors.append(self.get_extra_text(result["extra"]))

        return format_html_join(
            format_html("<br />"), "{}", ((error,) for error in errors)
        )


class RegexCheck(TargetCheckParametrized):
    check_id = "regex"
    default_disabled = True
    name = _("Regular expression")
    description = _("Translation does not match regular expression")

    @property
    def param_type(self):
        return single_value_flag(parse_regex)

    def check_target_params(self, sources, targets, unit, value):
        return any(not value.findall(target) for target in targets)

    def should_skip(self, unit):
        if super().should_skip(unit):
            return True
        return not self.get_value(unit).pattern

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return

        regex = self.get_value(unit)

        for match in regex.finditer(source):
            yield (match.start(), match.end(), match.group())

    def get_description(self, check_obj):
        unit = check_obj.unit
        if not self.has_value(unit):
            return super().get_description(check_obj)
        regex = self.get_value(unit)
        return format_html(
            escape(_("Does not match regular expression {}.")),
            format_html("<code>{}</code>", regex.pattern),
        )
