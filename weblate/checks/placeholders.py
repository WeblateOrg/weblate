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

from weblate.checks.base import Highlight, TargetCheckParametrized
from weblate.checks.parser import multi_value_flag, single_value_flag
from weblate.checks.utils import merge_highlight_spans, pair_markup_highlights
from weblate.utils.errors import report_error
from weblate.utils.regex import regex_findall, regex_finditer

if TYPE_CHECKING:
    from weblate.trans.models import Unit


def report_regex_timeout(message: str, unit: Unit) -> None:
    report_error(message, project=unit.translation.component.project)


def parse_regex(val):
    if isinstance(val, regex.Pattern):
        return val
    if not isinstance(val, str):
        val = val.pattern
    return regex.compile(val)


def parse_placeholders(val):
    placeholders = multi_value_flag(lambda x: x)(val)
    if any(
        not (placeholder if isinstance(placeholder, str) else placeholder.pattern)
        for placeholder in placeholders
    ):
        msg = "Empty placeholder"
        raise ValueError(msg)
    return placeholders


class PlaceholderCheck(TargetCheckParametrized):
    check_id = "placeholders"
    default_disabled = True
    name = gettext_lazy("Placeholders")
    description = gettext_lazy("Translation is missing some placeholders.")
    versions_changed = (
        ("4.3", "You can use regular expression as placeholder."),
        (
            "4.13",
            "With the ``case-insensitive`` flag, the placeholders are not case-sensitive.",
        ),
    )

    @property
    def param_type(self):
        return parse_placeholders

    def get_value(self, unit: Unit):
        placeholders = (
            regex.escape(param) if isinstance(param, str) else param.pattern
            for param in unit.all_flags.get_value_raw(self.enable_string)
        )
        placeholder_regex = "|".join(param for param in placeholders if param)
        if not placeholder_regex:
            return regex.compile(r"(?!)")
        return regex.compile(
            placeholder_regex,
            regex.IGNORECASE if "case-insensitive" in unit.all_flags else 0,
        )

    @staticmethod
    def get_matches(value, text: str):
        for match in regex_finditer(value, text, concurrent=True):
            yield match.group()

    def get_match_set(self, value, text: str, unit: Unit) -> set[str] | None:
        try:
            return set(self.get_matches(value, text))
        except TimeoutError:
            report_regex_timeout("Placeholder regex check timed out", unit)
            return None

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
        expected = self.get_match_set(value, sources[0], unit)
        if expected is None:
            return False
        if not expected and len(sources) > 1:
            expected = self.get_match_set(value, sources[-1], unit)
            if expected is None:
                return False
        plural_examples = SimpleLazyObject(lambda: unit.translation.plural.examples)

        if "case-insensitive" in unit.all_flags:
            diff_func = self.diff_case_insensitive
        else:
            diff_func = self.diff_case_sensitive

        missing = set()
        extra = set()

        for pluralno, target in enumerate(targets):
            found = self.get_match_set(value, target, unit)
            if found is None:
                return False
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
        if not self.has_value(unit):
            return

        regex_flags = regex.IGNORECASE if "case-insensitive" in unit.all_flags else 0
        spans: list[Highlight] = []

        # get raw list of patterns from unit to run each independently                    continue
        for param in unit.all_flags.get_value_raw(self.enable_string):
            if isinstance(param, str):
                if not param:
                    continue
                pattern = regex.compile(regex.escape(param), regex_flags)
            else:
                if not param.pattern:
                    continue
                pattern = regex.compile(param.pattern, regex_flags)

            try:
                spans.extend(
                    Highlight(match.start(), match.end(), match.group(), kind="grammar")
                    for match in regex_finditer(pattern, source)
                )
            except TimeoutError:
                report_regex_timeout("Placeholder regex highlight timed out", unit)
                return

        if not spans:
            return

        spans.sort(key=lambda highlight: (highlight.start, -highlight.end))
        yield from pair_markup_highlights(
            merge_highlight_spans(source, spans), group_prefix="placeholder"
        )

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
    versions_changed = (
        (
            "5.10",
            "Extended support for advanced regular expressions including Unicode codepoint properties.",
        ),
    )

    @property
    def param_type(self):
        return single_value_flag(parse_regex)

    def check_target_params(
        self, sources: list[str], targets: list[str], unit: Unit, value
    ):
        try:
            return any(not regex_findall(value, target) for target in targets)
        except TimeoutError:
            report_regex_timeout("Regular expression check timed out", unit)
            return False

    def should_skip(self, unit: Unit) -> bool:
        if super().should_skip(unit):
            return True
        return not self.get_value(unit).pattern

    def get_description(self, check_obj):
        unit = check_obj.unit
        if not self.has_value(unit):
            return super().get_description(check_obj)
        check_regex = self.get_value(unit)
        return format_html(
            escape(gettext_lazy("Does not match regular expression {}.")),
            format_html("<code>{}</code>", check_regex.pattern),
        )
