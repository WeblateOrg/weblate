# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import sentry_sdk
from django.http import Http404
from django.utils.html import conditional_escape, format_html, format_html_join
from django.utils.translation import gettext
from lxml import etree
from siphashc import siphash

from weblate.utils.docs import get_doc_url
from weblate.utils.xml import parse_xml

if TYPE_CHECKING:
    from collections.abc import Iterable


class Check:
    """Basic class for checks."""

    check_id = ""
    name = ""
    description = ""
    target = False
    source = False
    ignore_untranslated = True
    default_disabled = False
    propagates: bool = False
    param_type = None
    always_display = False
    batch_project_wide = False
    skip_suggestions = False

    def get_identifier(self):
        return self.check_id

    def get_propagated_value(self, unit):
        return None

    def get_propagated_units(self, unit, target: str | None = None):
        from weblate.trans.models import Unit

        return Unit.objects.none()

    def __init__(self):
        id_dash = self.check_id.replace("_", "-")
        self.url_id = f"check:{self.check_id}"
        self.doc_id = f"check-{id_dash}"
        self.enable_string = id_dash
        self.ignore_string = f"ignore-{id_dash}"

    def is_ignored(self, all_flags):
        return self.ignore_string in all_flags or "ignore-all-checks" in all_flags

    def should_skip(self, unit):
        """Check whether we should skip processing this unit."""
        all_flags = unit.all_flags
        # Is this check ignored
        if self.is_ignored(all_flags):
            return True

        # Is this disabled by default
        if self.default_disabled and self.enable_string not in all_flags:
            return True

        return False

    def should_display(self, unit):
        """Display the check always, not only when failing."""
        if self.ignore_untranslated and not unit.state:
            return False
        if self.should_skip(unit):
            return False
        # Display if enabled and the check is not triggered
        return self.always_display and self.check_id not in unit.all_checks_names

    def check_target(self, sources, targets, unit):
        """Check target strings."""
        # No checking of untranslated units (but we do check needs editing ones)
        if self.ignore_untranslated and (not unit.state or unit.readonly):
            return False
        if self.should_skip(unit):
            return False
        if self.check_id in unit.check_cache:
            return unit.check_cache[self.check_id]
        unit.check_cache[self.check_id] = result = self.check_target_unit(
            sources, targets, unit
        )
        return result

    def check_target_unit(self, sources, targets, unit):
        """Check single unit, handling plurals."""
        from weblate.lang.models import PluralMapper

        source_plural = unit.translation.component.source_language.plural
        target_plural = unit.translation.plural
        if len(sources) != source_plural.number or len(targets) != target_plural.number:
            return any(
                self.check_single(sources[-1], target, unit) for target in targets
            )
        plural_mapper = PluralMapper(source_plural, target_plural)
        return any(
            self.check_single(source, target, unit)
            for source, target in plural_mapper.zip(sources, targets, unit)
        )

    def check_single(self, source, target, unit):
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError

    def check_source(self, source, unit):
        """Check source strings."""
        if self.should_skip(unit):
            return False
        return self.check_source_unit(source, unit)

    def check_source_unit(self, source, unit):
        """Check source string."""
        raise NotImplementedError

    def check_chars(self, source, target, pos, chars):
        """Generic checker for chars presence."""
        try:
            src = source[pos]
            tgt = target[pos]
        except IndexError:
            return False

        return (src in chars) != (tgt in chars)

    def get_doc_url(self, user=None):
        """Return link to documentation."""
        return get_doc_url("user/checks", self.doc_id, user=user)

    def check_highlight(self, source, unit):
        """
        Return parts of the text that match to highlight them.

        Result is list that contains lists of two elements with start position of the
        match and the value of the match
        """
        return []

    def get_description(self, check_obj):
        return self.description

    def get_fixup(self, unit):
        return None

    def render(self, request, unit):
        raise Http404("Not supported")

    def get_cache_key(self, unit, pos):
        return "check:{}:{}:{}:{}".format(
            self.check_id,
            unit.pk,
            siphash("Weblate   Checks", unit.all_flags.format()),
            pos,
        )

    def get_replacement_function(self, unit):
        def strip_xml(content):
            try:
                tree = parse_xml(f"<x>{content}</x>")
            except etree.XMLSyntaxError:
                return content
            return etree.tostring(tree, encoding="unicode", method="text")

        def noop(content):
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


class BatchCheckMixin:
    def handle_batch(self, unit, component):
        component.batched_checks.add(self.check_id)
        return self.check_id in unit.all_checks_names

    def check_component(self, component):
        raise NotImplementedError

    def perform_batch(self, component):
        with sentry_sdk.start_span(op="check.perform_batch", description=self.check_id):
            self._perform_batch(component)

    def _perform_batch(self, component):
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


class TargetCheck(Check):
    """Basic class for target checks."""

    target = True

    def check_source_unit(self, source, unit):
        """We don't check source strings here."""
        return False

    def check_single(self, source, target, unit):
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError

    def format_value(self, value: str):
        from weblate.trans.templatetags.translations import Formatter

        fmt = Formatter(0, value, None, None, None, None, None)
        fmt.parse()
        return format_html(
            """<span class="hlcheck" data-value="{}">{}</span>""", value, fmt.format()
        )

    def get_values_text(self, message: str, values: Iterable[str]):
        return format_html_join(
            ", ",
            conditional_escape(message),
            ((self.format_value(value),) for value in sorted(values)),
        )

    def get_missing_text(self, values: Iterable[str]):
        return self.get_values_text(
            gettext("The following format strings are missing: {}"), values
        )

    def get_extra_text(self, values: Iterable[str]):
        return self.get_values_text(
            gettext("The following format strings are extra: {}"), values
        )


class SourceCheck(Check):
    """Basic class for source checks."""

    source = True

    def check_single(self, source, target, unit):
        """Target strings are checked in check_target_unit."""
        return False

    def check_source_unit(self, source, unit):
        """Check source string."""
        raise NotImplementedError


class TargetCheckParametrized(TargetCheck):
    """Basic class for target checks with flag value."""

    default_disabled = True

    def get_value(self, unit):
        return unit.all_flags.get_value(self.enable_string)

    def has_value(self, unit):
        return unit.all_flags.has_value(self.enable_string)

    def check_target_unit(self, sources, targets, unit):
        """Check flag value."""
        if unit.all_flags.has_value(self.enable_string):
            return self.check_target_params(
                sources, targets, unit, self.get_value(unit)
            )
        return False

    def check_target_params(self, sources, targets, unit, value):
        raise NotImplementedError

    def check_single(self, source, target, unit):
        """We don't check single phrase here."""
        return False


class CountingCheck(TargetCheck):
    """Check whether there is same count of given string."""

    string = ""

    def check_single(self, source, target, unit):
        if not target or not source:
            return False
        return source.count(self.string) != target.count(self.string)
