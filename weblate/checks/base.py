# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from weblate.utils.docs import get_doc_url


class Check(object):
    """Basic class for checks."""
    check_id = ''
    name = ''
    description = ''
    target = False
    source = False
    ignore_untranslated = True
    default_disabled = False
    severity = 'info'
    enable_check_value = False

    def get_identifier(self):
        return self.check_id

    def __init__(self):
        id_dash = self.check_id.replace('_', '-')
        self.url_id = 'check:{0}'.format(self.check_id)
        self.doc_id = 'check-{0}'.format(id_dash)
        self.enable_string = id_dash
        self.ignore_string = 'ignore-{0}'.format(id_dash)

    def should_skip(self, unit):
        """Check whether we should skip processing this unit"""
        # Is this disabled by default
        if self.default_disabled and self.enable_string not in unit.all_flags:
            return True

        # Is this check ignored
        if self.ignore_string in unit.all_flags:
            return True

        # Ignore target checks on templates
        if unit.translation.is_template:
            return True

        return False

    def check_target(self, sources, targets, unit):
        """Check target strings."""
        if self.enable_check_value:
            return self.check_target_unit_with_flag(
                sources, targets, unit
            )
        if self.should_skip(unit):
            return False
        # No checking of not translated units
        if self.ignore_untranslated and not unit.translated:
            return False
        return self.check_target_unit(sources, targets, unit)

    def check_target_unit_with_flag(self, sources, targets, unit):
        """Check flag value"""
        raise NotImplementedError()

    def check_target_unit(self, sources, targets, unit):
        """Check single unit, handling plurals."""
        # Check singular
        if self.check_single(sources[0], targets[0], unit):
            return True
        # Do we have more to check?
        if len(sources) == 1:
            return False
        # Check plurals against plural from source
        for target in targets[1:]:
            if self.check_single(sources[1], target, unit):
                return True
        # Check did not fire
        return False

    def check_single(self, source, target, unit):
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError()

    def check_source(self, source, unit):
        """Check source string"""
        raise NotImplementedError()

    def check_chars(self, source, target, pos, chars):
        """Generic checker for chars presence."""
        try:
            src = source[pos]
            tgt = target[pos]
        except IndexError:
            return False

        return (
            (src in chars and tgt not in chars) or
            (src not in chars and tgt in chars)
        )

    def check_ends(self, target, ends):
        """Check whether target ends with one of given ends."""
        for end in ends:
            if target.endswith(end):
                return True
        return False

    def is_language(self, unit, vals):
        """Detect whether language is in given list, ignores variants."""
        return unit.translation.language.code.split('_')[0] in vals

    def get_doc_url(self):
        """Return link to documentation."""
        return get_doc_url('user/checks', self.doc_id)

    def check_highlight(self, source, unit):
        """Return parts of the text that match to hightlight them
        return is table that contains lists of two elements with
        start position of the match and the value of the match
        """
        return []


class TargetCheck(Check):
    """Basic class for target checks."""
    target = True

    def check_target_unit_with_flag(self, sources, targets, unit):
        """We don't check flag value here."""
        return False

    def check_source(self, source, unit):
        """We don't check source strings here."""
        return False

    def check_single(self, source, target, unit):
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError()


class SourceCheck(Check):
    """Basic class for source checks."""
    source = True

    def check_target_unit_with_flag(self, sources, targets, unit):
        """We don't check flag value here."""
        return False

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False

    def check_source(self, source, unit):
        """Check source string"""
        raise NotImplementedError()


class TargetCheckWithFlag(Check):
    """Basic class for target checks with flag value."""
    default_disabled = True
    enable_check_value = True
    target = True

    def check_target_unit_with_flag(self, sources, targets, unit):
        """Check flag value"""
        raise NotImplementedError()

    def check_single(self, source, target, unit):
        """We don't check single phrase here."""
        return False

    def check_source(self, source, unit):
        """We don't check source strings here."""
        return False


class CountingCheck(TargetCheck):
    """Check whether there is same count of given string."""
    string = None

    def check_single(self, source, target, unit):
        if not target or not source:
            return False
        return source.count(self.string) != target.count(self.string)
