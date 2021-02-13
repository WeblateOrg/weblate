#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django.http import Http404
from siphashc import siphash

from weblate.utils.docs import get_doc_url


class Check:
    """Basic class for checks."""

    check_id = ""
    name = ""
    description = ""
    target = False
    source = False
    ignore_untranslated = True
    default_disabled = False
    propagates = False
    param_type = None
    always_display = False

    def get_identifier(self):
        return self.check_id

    def __init__(self):
        id_dash = self.check_id.replace("_", "-")
        self.url_id = f"check:{self.check_id}"
        self.doc_id = f"check-{id_dash}"
        self.enable_string = id_dash
        self.ignore_string = f"ignore-{id_dash}"

    def should_skip(self, unit):
        """Check whether we should skip processing this unit."""
        # Is this check ignored
        if self.ignore_string in unit.all_flags:
            return True

        # Is this disabled by default
        if self.default_disabled and self.enable_string not in unit.all_flags:
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
        # No checking of not translated units (but we do check needs editing ones)
        if self.ignore_untranslated and not unit.state:
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
        source = sources[0]
        # Check singular
        if self.check_single(source, targets[0], unit):
            return True
        # Do we have more to check?
        if len(sources) > 1:
            source = sources[1]
        # Check plurals against plural from source
        for target in targets[1:]:
            if self.check_single(source, target, unit):
                return True
        # Check did not fire
        return False

    def check_single(self, source, target, unit):
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError()

    def check_source(self, source, unit):
        """Check source strings."""
        if self.should_skip(unit):
            return False
        return self.check_source_unit(source, unit)

    def check_source_unit(self, source, unit):
        """Check source string."""
        raise NotImplementedError()

    def check_chars(self, source, target, pos, chars):
        """Generic checker for chars presence."""
        try:
            src = source[pos]
            tgt = target[pos]
        except IndexError:
            return False

        return (src in chars) != (tgt in chars)

    def is_language(self, unit, vals):
        """Detect whether language is in given list, ignores variants."""
        return unit.translation.language.base_code in vals

    def get_doc_url(self, user=None):
        """Return link to documentation."""
        return get_doc_url("user/checks", self.doc_id, user=user)

    def check_highlight(self, source, unit):
        """Return parts of the text that match to hightlight them.

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
        flags = unit.all_flags
        if not flags.has_value("replacements"):
            return lambda text: text

        # Parse the flag
        replacements = flags.get_value("replacements")
        # Create dict from that
        replacements = dict(
            replacements[pos : pos + 2] for pos in range(0, len(replacements), 2)
        )

        # Build regexp matcher
        pattern = re.compile("|".join(re.escape(key) for key in replacements.keys()))

        return lambda text: pattern.sub(lambda m: replacements[m.group(0)], text)

    def handle_batch(self, unit, component):
        component.batched_checks.add(self.check_id)
        return self.check_id in unit.all_checks_names

    def check_component(self, component):
        return []

    def perform_batch(self, component):
        from weblate.checks.models import Check

        handled = set()
        changed = False
        create = []
        for unit in self.check_component(component):
            # Handle ignore flags
            if self.should_skip(unit):
                continue
            handled.add(unit.pk)

            # Check is already there
            if self.check_id in unit.all_checks_names:
                continue

            create.append(Check(unit=unit, dismissed=False, check=self.check_id))
            changed = True

        Check.objects.bulk_create(create, batch_size=500, ignore_conflicts=True)

        # Delete stale checks
        changed |= (
            Check.objects.filter(
                unit__translation__component=component,
                check=self.check_id,
            )
            .exclude(unit_id__in=handled)
            .delete()[0]
        )

        # Invalidate stats in case there were changes
        if changed:
            component.invalidate_cache()


class TargetCheck(Check):
    """Basic class for target checks."""

    target = True

    def check_source_unit(self, source, unit):
        """We don't check source strings here."""
        return False

    def check_single(self, source, target, unit):
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError()


class SourceCheck(Check):
    """Basic class for source checks."""

    source = True

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False

    def check_source_unit(self, source, unit):
        """Check source string."""
        raise NotImplementedError()


class TargetCheckParametrized(Check):
    """Basic class for target checks with flag value."""

    default_disabled = True
    target = True

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
        raise NotImplementedError()

    def check_single(self, source, target, unit):
        """We don't check single phrase here."""
        return False

    def check_source_unit(self, source, unit):
        """We don't check source strings here."""
        return False


class CountingCheck(TargetCheck):
    """Check whether there is same count of given string."""

    string = ""

    def check_single(self, source, target, unit):
        if not target or not source:
            return False
        return source.count(self.string) != target.count(self.string)
