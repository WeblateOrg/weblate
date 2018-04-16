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

import re

from django.utils.translation import ugettext_lazy as _

from weblate.checks.base import TargetCheck

PYTHON_PRINTF_MATCH = re.compile(
    r'''
    %(                          # initial %
          (?:\((?P<key>\w+)\))?    # Python style variables, like %(var)s
    (?P<fullvar>
        [+#-]*                  # flags
        (?:\d+)?                # width
        (?:\.\d+)?              # precision
        (hh|h|l|ll)?         # length formatting
        (?P<type>[a-zA-Z%]))        # type (%s, %d, etc.)
    )''',
    re.VERBOSE
)


PHP_PRINTF_MATCH = re.compile(
    r'''
    %(                          # initial %
          (?:(?P<ord>\d+)\$)?   # variable order, like %1$s
    (?P<fullvar>
        [+#-]*                  # flags
        (?:\d+)?                # width
        (?:\.\d+)?              # precision
        (hh|h|l|ll)?         # length formatting
        (?P<type>[a-zA-Z%]))        # type (%s, %d, etc.)
    )''',
    re.VERBOSE
)


C_PRINTF_MATCH = re.compile(
    r'''
    %(                          # initial %
          (?:(?P<ord>\d+)\$)?   # variable order, like %1$s
    (?P<fullvar>
        [+#'-]*                 # flags
        (?:\d+)?                # width
        (?:\.\d+)?              # precision
        (hh|h|l|ll)?         # length formatting
        (?P<type>[a-zA-Z%]))        # type (%s, %d, etc.)
    )''',
    re.VERBOSE
)

PYTHON_BRACE_MATCH = re.compile(
    r'''
    {(                                  # initial {
        |                               # blank for position based
        (?P<field>
            [0-9]+|                     # numerical
            [_A-Za-z][_0-9A-Za-z]*      # identifier
        )
        (?P<attr>
            \.[_A-Za-z][_0-9A-Za-z]*    # attribute identifier
            |\[[^]]+\]                  # index identifier

        )*
        (?P<conversion>
            ![rsa]
        )?
        (?P<format_spec>
            :
            .?                          # fill
            [<>=^]?                     # align
            [+ -]?                      # sign
            [#]?                        # alternate
            0?                          # 0 prefix
            (?:[1-9][0-9]*)?            # width
            ,?                          # , separator
            (?:\.[1-9][0-9]*)?          # precision
            [bcdeEfFgGnosxX%]?          # type
        )?
    )}                          # trailing }
    ''',
    re.VERBOSE
)


class BaseFormatCheck(TargetCheck):
    """Base class for fomat string checks."""
    regexp = None
    default_disabled = True
    severity = 'danger'

    def check_target_unit(self, sources, targets, unit):
        """Check single unit, handling plurals."""
        # Special case languages with single plural form
        if len(sources) > 1 and len(targets) == 1:
            return self.check_format(
                sources[1],
                targets[0],
                False
            )

        # Check singular
        singular_check = self.check_format(
            sources[0],
            targets[0],
            len(sources) > 1
        )
        if singular_check:
            return True

        # Do we have more to check?
        if len(sources) == 1:
            return False

        # Check plurals against plural from source
        for target in targets[1:]:
            plural_check = self.check_format(
                sources[1],
                target,
                False
            )
            if plural_check:
                return True

        # Check did not fire
        return False

    def cleanup_string(self, text):
        """Remove locale specific code from format string"""
        if '\'' in text:
            return text.replace('\'', '')
        return text

    def check_format(self, source, target, ignore_missing):
        """Generic checker for format strings."""
        if not target or not source:
            return False

        uses_position = True

        # We ignore %% in the matches as this is really not relevant. However
        # it needs to be matched to prevent handling %%s as %s.

        # Calculate value
        src_matches = [
            self.cleanup_string(x[0])
            for x in self.regexp.findall(source)
            if x[0] != '%'
        ]
        if src_matches:
            uses_position = max(
                [self.is_position_based(x) for x in src_matches]
            )

        tgt_matches = [
            self.cleanup_string(x[0])
            for x in self.regexp.findall(target)
            if x[0] != '%'
        ]

        if not uses_position:
            src_matches = set(src_matches)
            tgt_matches = set(tgt_matches)

        if src_matches != tgt_matches:
            # We can ignore missing format strings
            # for first of plurals
            if ignore_missing and tgt_matches < src_matches:
                return False
            return True

        return False

    def is_position_based(self, string):
        raise NotImplementedError()

    def check_single(self, source, target, unit):
        """We don't check target strings here."""
        return False

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return []
        ret = []
        match_objects = self.regexp.finditer(source)
        for match in match_objects:
            ret.append((match.start(), match.end(), match.group()))
        return ret


class PythonFormatCheck(BaseFormatCheck):
    """Check for Python format string"""
    check_id = 'python_format'
    name = _('Python format')
    description = _('Python format string does not match source')
    regexp = PYTHON_PRINTF_MATCH

    def is_position_based(self, string):
        return '(' not in string and string != '%'


class PHPFormatCheck(BaseFormatCheck):
    """Check for PHP format string"""
    check_id = 'php_format'
    name = _('PHP format')
    description = _('PHP format string does not match source')
    regexp = PHP_PRINTF_MATCH

    def is_position_based(self, string):
        return '$' not in string and string != '%'


class CFormatCheck(BaseFormatCheck):
    """Check for C format string"""
    check_id = 'c_format'
    name = _('C format')
    description = _('C format string does not match source')
    regexp = C_PRINTF_MATCH

    def is_position_based(self, string):
        return '$' not in string and string != '%'


class PerlFormatCheck(BaseFormatCheck):
    """Check for Perl format string"""
    check_id = 'perl_format'
    name = _('Perl format')
    description = _('Perl format string does not match source')
    regexp = C_PRINTF_MATCH

    def is_position_based(self, string):
        return '$' not in string and string != '%'


class JavascriptFormatCheck(CFormatCheck):
    """Check for Javascript format string"""
    check_id = 'javascript_format'
    name = _('Javascript format')
    description = _('Javascript format string does not match source')


class PythonBraceFormatCheck(BaseFormatCheck):
    """Check for Python format string"""
    check_id = 'python_brace_format'
    name = _('Python brace format')
    description = _('Python brace format string does not match source')
    regexp = PYTHON_BRACE_MATCH

    def is_position_based(self, string):
        return string == ''
