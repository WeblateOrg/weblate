# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import regex
from django.utils.functional import SimpleLazyObject
from django.utils.html import escape, format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy

from weblate.checks.base import TargetCheckParametrized
from weblate.checks.parser import multi_value_flag, single_value_flag

if TYPE_CHECKING:
    from weblate.trans.models import Unit


def parse_regex(val):
    if isinstance(val, str):
        return regex.compile(val)
    return val


class PlaceholderCheck(TargetCheckParametrized):
    check_id = "placeholders"
    default_disabled = True
    name = gettext_lazy("Placeholders")
    description = gettext_lazy("Translation is missing some placeholders.")

    @property
    def param_type(self):
        return multi_value_flag(lambda x: x)

    def get_value(self, unit: Unit):
        return regex.compile(
            "|".join(
                regex.escape(param) if isinstance(param, str) else param.pattern
                for param in super().get_value(unit)
            ),
            regex.IGNORECASE if "case-insensitive" in unit.all_flags else 0,
        )

    @staticmethod
    def get_matches(value, text: str):
        for match in value.finditer(text, concurrent=True):
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

    def check_target_unit(  # type: ignore[override]
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> Literal[False] | dict[str, Any]:
        # TODO: this is type annotation hack, instead the check should have a proper return type
        return super().check_target_unit(sources, targets, unit)  # type: ignore[return-value]

    def check_target_params(  # type: ignore[override]
        self, sources: list[str], targets: list[str], unit: Unit, value
    ) -> Literal[False] | dict[str, Any]:
        expected = set(self.get_matches(value, sources[0]))
        if not expected and len(sources) > 1:
            expected = set(self.get_matches(value, sources[-1]))
        plural_examples = SimpleLazyObject(lambda: unit.translation.plural.examples)

        if "case-insensitive" in unit.all_flags:
            diff_func = self.diff_case_insensitive
        else:
            diff_func = self.diff_case_sensitive

        missing = set()
        extra = set()

        for pluralno, target in enumerate(targets):
            found = set(self.get_matches(value, target))
            diff = diff_func(expected, found)
            plural_example = plural_examples[pluralno]
            # Allow to skip format string in case there is single plural or in special
            # case of 0, 1 plural. It is technically wrong, but in many cases there
            # won't be 0 so don't trigger too many false positives
            if len(targets) == 1 or (
                len(plural_example) > 1 and plural_example != ["0", "1"]
            ):
                missing.update(diff[0])
            extra.update(diff[1])

        if missing or extra:
            return {"missing": missing, "extra": extra}
        return False

    def check_highlight(self, source: str, unit: Unit):
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
            mark_safe("<br />"),
            "{}",
            ((error,) for error in errors),
        )


class RegexCheck(TargetCheckParametrized):
    check_id = "regex"
    default_disabled = True
    name = gettext_lazy("Regular expression")
    description = gettext_lazy("Translation does not match regular expression.")

    @property
    def param_type(self):
        return single_value_flag(parse_regex)

    def check_target_params(
        self, sources: list[str], targets: list[str], unit: Unit, value
    ):
        return any(not value.findall(target) for target in targets)

    def should_skip(self, unit: Unit) -> bool:
        if super().should_skip(unit):
            return True
        return not self.get_value(unit).pattern

    def check_highlight(self, source: str, unit: Unit):
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
            escape(gettext_lazy("Does not match regular expression {}.")),
            format_html("<code>{}</code>", regex.pattern),
        )
