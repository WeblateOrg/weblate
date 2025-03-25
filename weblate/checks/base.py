# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import sentry_sdk
from django.http import Http404
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext
from lxml import etree
from siphashc import siphash

from weblate.utils.docs import get_doc_url
from weblate.utils.html import format_html_join_comma
from weblate.utils.xml import parse_xml

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.trans.models import Component, Unit

    from .flags import Flags
    from .models import Check


class MissingExtraDict(TypedDict, total=False):
    missing: list[str]
    extra: list[str]
    errors: list[str]


class BaseCheck:
    """Basic class for checks."""

    check_id = ""
    name: StrOrPromise = ""
    description: StrOrPromise = ""
    target = False
    source = False
    glossary = False
    ignore_untranslated = True
    ignore_readonly = True
    default_disabled = False
    propagates: Literal["source", "target"] | None = None
    param_type = None
    always_display = False
    batch_project_wide = False
    skip_suggestions = False
    extra_enable_strings: list[str] = []

    def get_identifier(self) -> str:
        return self.check_id

    def __init__(self) -> None:
        id_dash = self.check_id.replace("_", "-")
        self.url_id = f"check:{self.check_id}"
        self.doc_id = f"check-{id_dash}"
        self.enable_string = id_dash
        self.ignore_string = f"ignore-{id_dash}"

    def is_ignored(self, all_flags: Flags) -> bool:
        return self.ignore_string in all_flags or "ignore-all-checks" in all_flags

    def should_skip(self, unit: Unit) -> bool:
        """Check whether we should skip processing this unit."""
        all_flags = unit.all_flags
        # Is this check ignored
        if self.is_ignored(all_flags):
            return True

        # Is this disabled by default
        if self.default_disabled:
            return not all_flags.has_any(
                {self.enable_string, *self.extra_enable_strings}
            )

        # Enabled by default
        return False

    def ignore_state(self, unit: Unit) -> bool:
        if unit.readonly and not self.ignore_readonly:
            return False
        return self.ignore_untranslated and (not unit.state or unit.readonly)

    def should_display(self, unit: Unit) -> bool:
        """Display the check always, not only when failing."""
        if self.ignore_state(unit):
            return False
        if self.should_skip(unit):
            return False
        # Display if enabled and the check is not triggered
        return self.always_display and self.check_id not in unit.all_checks_names

    def check_target(self, sources: list[str], targets: list[str], unit: Unit) -> bool:
        """Check target strings."""
        # No checking of untranslated units (but we do check needs editing ones)
        if self.ignore_state(unit):
            return False
        if self.should_skip(unit):
            return False
        if self.check_id in unit.check_cache:
            return unit.check_cache[self.check_id]
        unit.check_cache[self.check_id] = result = self.check_target_unit(
            sources, targets, unit
        )
        return result

    def check_target_generator(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> Generator[bool | MissingExtraDict]:
        """Check single unit, handling plurals."""
        from weblate.lang.models import PluralMapper

        source_plural = unit.translation.component.source_language.plural
        target_plural = unit.translation.plural
        if len(sources) != source_plural.number or len(targets) != target_plural.number:
            for target in targets:
                yield self.check_single(sources[-1], target, unit)
        else:
            plural_mapper = PluralMapper(source_plural, target_plural)
            for source, target in plural_mapper.zip(sources, targets, unit):
                yield self.check_single(source, target, unit)

    def check_target_unit(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> bool:
        """Check single unit, handling plurals."""
        return any(self.check_target_generator(sources, targets, unit))

    def check_single(
        self, source: str, target: str, unit: Unit
    ) -> bool | MissingExtraDict:
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError

    def check_source(self, sources: list[str], unit: Unit) -> bool:
        """Check source strings."""
        if self.should_skip(unit):
            return False
        return self.check_source_unit(sources, unit)

    def check_source_unit(self, sources: list[str], unit: Unit) -> bool:
        """Check source string."""
        raise NotImplementedError

    def check_chars(self, source: str, target: str, pos: int, chars: set[str]) -> bool:
        """Check whether characters are present."""
        try:
            src = source[pos]
            tgt = target[pos]
        except IndexError:
            return False

        return (src in chars) != (tgt in chars)

    def get_doc_url(self, user: User | None = None) -> str:
        """Return link to documentation."""
        return get_doc_url("user/checks", self.doc_id, user=user)

    def check_highlight(self, source: str, unit: Unit):
        """
        Return parts of the text that match to highlight them.

        Result is list that contains lists of two elements with start position of the
        match and the value of the match
        """
        return []

    def get_description(self, check_obj: Check) -> StrOrPromise:
        return self.description

    def get_fixup(self, unit: Unit) -> Iterable[tuple[str, str, str]] | None:
        return None

    def render(self, request: AuthenticatedHttpRequest, unit: Unit) -> StrOrPromise:
        msg = "Not supported"
        raise Http404(msg)

    def get_cache_key(self, unit: Unit, pos: int) -> str:
        return "check:{}:{}:{}:{}".format(
            self.check_id,
            unit.pk,
            siphash("Weblate   Checks", unit.all_flags.format()),
            pos,
        )

    def get_replacement_function(self, unit: Unit):
        def strip_xml(content: str) -> str:
            try:
                tree = parse_xml(f"<x>{content}</x>")
            except etree.XMLSyntaxError:
                return content
            return etree.tostring(tree, encoding="unicode", method="text")

        def noop(content: str) -> str:
            return content

        flags = unit.all_flags

        # chain XML striping if needed
        replacement = strip_xml if "xml-text" in flags else noop

        if not flags.has_value("replacements"):
            return replacement

        # Parse the flag
        replacements = flags.get_value("replacements")
        # Create dict from that
        replacements = dict(
            replacements[pos : pos + 2] for pos in range(0, len(replacements), 2)
        )

        # Build regexp matcher
        pattern = re.compile("|".join(re.escape(key) for key in replacements))

        return lambda text: pattern.sub(
            lambda m: replacements[m.group(0)], replacement(text)
        )


class BatchCheckMixin(BaseCheck):
    def handle_batch(self, unit: Unit, component: Component) -> bool:
        component.batched_checks.add(self.check_id)
        return self.check_id in unit.all_checks_names

    def check_component(self, component: Component) -> Iterable[Unit]:
        raise NotImplementedError

    def perform_batch(self, component: Component) -> None:
        with sentry_sdk.start_span(op="check.perform_batch", name=self.check_id):
            self._perform_batch(component)

    def _perform_batch(self, component: Component) -> None:
        from weblate.checks.models import Check
        from weblate.trans.models import Component

        handled = set()
        create = []
        components = {}
        for unit in self.check_component(component):
            # Handle ignore flags
            if self.should_skip(unit):
                continue
            handled.add(unit.pk)

            # Check is already there
            if self.check_id in unit.all_checks_names:
                continue

            create.append(Check(unit=unit, dismissed=False, name=self.check_id))
            components[unit.translation.component.id] = unit.translation.component

        Check.objects.bulk_create(create, batch_size=500, ignore_conflicts=True)

        # Delete stale checks
        stale_checks = Check.objects.exclude(unit_id__in=handled)
        if self.batch_project_wide and component.allow_translation_propagation:
            stale_checks = stale_checks.filter(
                unit__translation__component__project=component.project,
                unit__translation__component__allow_translation_propagation=True,
                name=self.check_id,
            )
            for current in Component.objects.filter(
                pk__in=stale_checks.values_list(
                    "unit__translation__component", flat=True
                )
            ):
                components[current.pk] = current
            stale_checks.delete()
        else:
            stale_checks = stale_checks.filter(
                unit__translation__component=component,
                name=self.check_id,
            )
            if stale_checks.delete()[0]:
                components[component.id] = component

        # Invalidate stats in case there were changes
        for current in components.values():
            current.invalidate_cache()


class TargetCheck(BaseCheck):
    """Basic class for target checks."""

    target = True

    def check_source_unit(self, sources: list[str], unit: Unit) -> bool:
        """We don't check source strings here."""
        return False

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError

    def format_value(self, value: str) -> StrOrPromise:
        from weblate.trans.templatetags.translations import Formatter

        fmt = Formatter(0, value, None, None, None, None, None)
        fmt.parse()
        return format_html(
            """<span class="hlcheck" data-value="{}">{}</span>""", value, fmt.format()
        )

    def get_values_text(self, message: str, values: Iterable[str]) -> StrOrPromise:
        return format_html(
            message,
            format_html_join_comma(
                "{}",
                ((self.format_value(value),) for value in sorted(values)),
            ),
        )

    def get_missing_text(self, values: Iterable[str]) -> StrOrPromise:
        return self.get_values_text(
            gettext("The following format strings are missing: {}"), values
        )

    def get_extra_text(self, values: Iterable[str]) -> StrOrPromise:
        return self.get_values_text(
            gettext("The following format strings are extra: {}"), values
        )

    def get_errors_text(self, values: Iterable[str]) -> StrOrPromise:
        return format_html_join(
            mark_safe("<br />"),
            "{}",
            (
                (value,)
                for value in (gettext("The following errors were found:"), *values)
            ),
        )

    def format_string(self, string: str) -> str:
        """Format parsed format string into human readable value."""
        return string

    def format_result(self, result: MissingExtraDict) -> Iterable[StrOrPromise]:
        if missing := result.get("missing"):
            yield self.get_missing_text(self.format_string(x) for x in set(missing))
        if extra := result.get("extra"):
            yield self.get_extra_text(self.format_string(x) for x in set(extra))
        if errors := result.get("errors"):
            yield self.get_errors_text(set(errors))


class SourceCheck(BaseCheck):
    """Basic class for source checks."""

    source = True

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Target strings are checked in check_target_unit."""
        return False

    def check_source_unit(self, sources: list[str], unit: Unit) -> bool:
        """Check source string."""
        raise NotImplementedError


class TargetCheckParametrized(TargetCheck):
    """Basic class for target checks with flag value."""

    default_disabled = True

    def get_value(self, unit: Unit) -> Any:  # noqa: ANN401
        return unit.all_flags.get_value(self.enable_string)

    def has_value(self, unit: Unit) -> bool:
        return unit.all_flags.has_value(self.enable_string)

    def check_target_unit(
        self, sources: list[str], targets: list[str], unit: Unit
    ) -> bool:
        """Check flag value."""
        if unit.all_flags.has_value(self.enable_string):
            return self.check_target_params(
                sources, targets, unit, self.get_value(unit)
            )
        return False

    def check_target_params(
        self,
        sources: list[str],
        targets: list[str],
        unit: Unit,
        value: Any,  # noqa: ANN401
    ) -> bool:
        raise NotImplementedError

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """We don't check single phrase here."""
        return False


class CountingCheck(TargetCheck):
    """Check whether there is same count of given string."""

    string = ""

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        if not target or not source:
            return False
        return source.count(self.string) != target.count(self.string)
