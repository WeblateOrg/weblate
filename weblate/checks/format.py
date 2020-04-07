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

from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheck

PYTHON_PRINTF_MATCH = re.compile(
    r"""
    %(                          # initial %
          (?:\((?P<key>[^)]+)\))?    # Python style variables, like %(var)s
    (?P<fullvar>
        [ +#-]*                 # flags
        (?:\d+)?                # width
        (?:\.\d+)?              # precision
        (hh|h|l|ll)?         # length formatting
        (?P<type>[a-zA-Z%])        # type (%s, %d, etc.)
        |)                      # incomplete format string
    )""",
    re.VERBOSE,
)


PHP_PRINTF_MATCH = re.compile(
    r"""
    %(                          # initial %
          (?:(?P<ord>\d+)\$)?   # variable order, like %1$s
    (?P<fullvar>
        [ +#-]*                 # flags
        (?:\d+)?                # width
        (?:\.\d+)?              # precision
        (hh|h|l|ll)?         # length formatting
        (?P<type>[a-zA-Z%])        # type (%s, %d, etc.)
        |)                      # incomplete format string
    )""",
    re.VERBOSE,
)


C_PRINTF_MATCH = re.compile(
    r"""
    %(                          # initial %
          (?:(?P<ord>\d+)\$)?   # variable order, like %1$s
    (?P<fullvar>
        [ +#'-]*                # flags
        (?:\d+)?                # width
        (?:\.\d+)?              # precision
        (hh|h|l|ll)?         # length formatting
        (?P<type>[a-zA-Z%])        # type (%s, %d, etc.)
        |)                      # incomplete format string
    )""",
    re.VERBOSE,
)

PYTHON_BRACE_MATCH = re.compile(
    r"""
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
    """,
    re.VERBOSE,
)

C_SHARP_MATCH = re.compile(
    r"""
        {                               # initial {
        (?P<arg>\d+)                    # variable order
        (?P<width>
            [,-?\s]+                    # flags
            (?:\d+)?                    # width
            (?:\.\d+)?                  # precision
        )?
        (?P<format>
            :                           # ':' identifier
            ((
                [a-zA-Z0#.,\s]*         # type
                (?:\d+)?                # numerical
            ))?
        )?
    }                                   # Ending }
    """,
    re.VERBOSE,
)

JAVA_MATCH = re.compile(
    r"""
        %((?![\s])                     # initial % (no space after)
          (?:(?P<ord>\d+)\$)?          # variable order, like %1$s
    (?P<fullvar>
        [-.#+0,(]*                     # flags
        (?:\d+)?                       # width
        (?:\.\d+)?                     # precision
        (?P<type>
            ((?<![tT])[tT][A-Za-z]|[A-Za-z])) # type (%s, %d, %te, etc.)
       )
    )
    """,
    re.VERBOSE,
)

JAVA_MESSAGE_MATCH = re.compile(
    r"""
    {                                   # initial {
        (?P<arg>\d+)                    # variable order
        \s*
        (
        ,\s*(?P<format>[a-z]+)          # format type
        (,\s*(?P<style>\S+))?            # format style
        )?
        \s*
    }                                   # Ending }
    """,
    re.VERBOSE,
)

I18NEXT_MATCH = re.compile(
    r"""
    (
    \$t\((.+?)\)      # nesting
    |
    {{(.+?)}}         # interpolation
    )
    """,
    re.VERBOSE,
)

PERCENT_MATCH = re.compile(r"(%([a-zA-Z0-9_]+)%)")

WHITESPACE = re.compile(r"\s+")


class BaseFormatCheck(TargetCheck):
    """Base class for fomat string checks."""

    regexp = None
    default_disabled = True
    severity = "danger"

    def check_target_unit(self, sources, targets, unit):
        """Check single unit, handling plurals."""
        return any(self.check_generator(sources, targets, unit))

    def check_generator(self, sources, targets, unit):
        # Special case languages with single plural form
        if len(sources) > 1 and len(targets) == 1:
            yield self.check_format(sources[1], targets[0], False)
            return

        # Check singular
        yield self.check_format(
            sources[0],
            targets[0],
            len(sources) > 1 and len(unit.translation.plural.examples[0]) == 1,
        )

        # Do we have more to check?
        if len(sources) == 1:
            return

        # Check plurals against plural from source
        for i, target in enumerate(targets[1:]):
            yield self.check_format(
                sources[1], target, len(unit.translation.plural.examples[i + 1]) == 1
            )

    def format_string(self, string):
        return string

    def cleanup_string(self, text):
        return text

    def normalize(self, matches):
        return matches

    def check_format(self, source, target, ignore_missing):
        """Generic checker for format strings."""
        if not target or not source:
            return False

        uses_position = True

        # Calculate value
        src_matches = [self.cleanup_string(x[0]) for x in self.regexp.findall(source)]
        if src_matches:
            uses_position = any((self.is_position_based(x) for x in src_matches))

        tgt_matches = [self.cleanup_string(x[0]) for x in self.regexp.findall(target)]

        if not uses_position:
            src_matches = set(src_matches)
            tgt_matches = set(tgt_matches)

        if src_matches != tgt_matches:
            # Ignore mismatch in percent position
            if self.normalize(src_matches) == self.normalize(tgt_matches):
                return False
            # We can ignore missing format strings
            # for first of plurals
            if ignore_missing and tgt_matches < src_matches:
                return False
            if not uses_position:
                return src_matches - tgt_matches
            result = []
            for i in range(min(len(src_matches), len(tgt_matches))):
                if src_matches[i] != tgt_matches[i]:
                    result.append(src_matches[i])
            result.extend(src_matches[len(tgt_matches) :])
            result.extend(tgt_matches[len(src_matches) :])
            return result
        return False

    def is_position_based(self, string):
        return False

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

    def format_result(self, result):
        return _("Following format strings are wrong: %s") % ", ".join(
            self.format_string(x) for x in result
        )

    def get_description(self, check_obj):
        unit = check_obj.unit
        checks = self.check_generator(
            unit.get_source_plurals(), unit.get_target_plurals(), unit
        )
        for result in checks:
            if result:
                return self.format_result(result)
        return super().get_description(check_obj)


class BasePrintfCheck(BaseFormatCheck):
    """Base class for printf based format checks."""

    def is_position_based(self, string):
        raise NotImplementedError()

    def normalize(self, matches):
        return [m for m in matches if m != "%"]

    def format_string(self, string):
        return "%{}".format(string)

    def cleanup_string(self, text):
        """Remove locale specific code from format string."""
        if "'" in text:
            return text.replace("'", "")
        return text


class PythonFormatCheck(BasePrintfCheck):
    """Check for Python format string."""

    check_id = "python_format"
    name = _("Python format")
    description = _("Python format string does not match source")
    regexp = PYTHON_PRINTF_MATCH

    def is_position_based(self, string):
        return "(" not in string and string != "%"


class PHPFormatCheck(BasePrintfCheck):
    """Check for PHP format string."""

    check_id = "php_format"
    name = _("PHP format")
    description = _("PHP format string does not match source")
    regexp = PHP_PRINTF_MATCH

    def is_position_based(self, string):
        return "$" not in string and string != "%"


class CFormatCheck(BasePrintfCheck):
    """Check for C format string."""

    check_id = "c_format"
    name = _("C format")
    description = _("C format string does not match source")
    regexp = C_PRINTF_MATCH

    def is_position_based(self, string):
        return "$" not in string and string != "%"


class PerlFormatCheck(BasePrintfCheck):
    """Check for Perl format string."""

    check_id = "perl_format"
    name = _("Perl format")
    description = _("Perl format string does not match source")
    regexp = C_PRINTF_MATCH

    def is_position_based(self, string):
        return "$" not in string and string != "%"


class JavaScriptFormatCheck(CFormatCheck):
    """Check for JavaScript format string."""

    check_id = "javascript_format"
    name = _("JavaScript format")
    description = _("JavaScript format string does not match source")


class PythonBraceFormatCheck(BaseFormatCheck):
    """Check for Python format string."""

    check_id = "python_brace_format"
    name = _("Python brace format")
    description = _("Python brace format string does not match source")
    regexp = PYTHON_BRACE_MATCH

    def is_position_based(self, string):
        return string == ""

    def format_string(self, string):
        return "{%s}" % string


class CSharpFormatCheck(BaseFormatCheck):
    """Check for C# format string."""

    check_id = "c_sharp_format"
    name = _("C# format")
    description = _("C# format string does not match source")
    regexp = C_SHARP_MATCH

    def is_position_based(self, string):
        return string == ""

    def format_string(self, string):
        return "{%s}" % string


class JavaFormatCheck(BasePrintfCheck):
    """Check for Java format string."""

    check_id = "java_format"
    name = _("Java format")
    description = _("Java format string does not match source")
    regexp = JAVA_MATCH

    def is_position_based(self, string):
        return "$" not in string and string != "%"


class JavaMessageFormatCheck(BaseFormatCheck):
    """Check for Java MessageFormat string."""

    check_id = "java_messageformat"
    name = _("Java MessageFormat")
    description = _("Java MessageFormat string does not match source")
    regexp = JAVA_MESSAGE_MATCH

    def format_string(self, string):
        return "{%s}" % string

    def should_skip(self, unit):
        if "auto-java-messageformat" in unit.all_flags and "{0" in unit.source:
            return False

        return super().should_skip(unit)

    def check_format(self, source, target, ignore_missing):
        """Generic checker for format strings."""
        if not target or not source:
            return False

        # Even number of quotes
        if target.count("'") % 2 != 0:
            return ["'"]

        return super().check_format(source, target, ignore_missing)

    def format_result(self, result):
        if "'" in result:
            return _("You need to pair up an apostrophe with another one.")
        return super().format_result(result)


class I18NextInterpolationCheck(BaseFormatCheck):
    check_id = "i18next_interpolation"
    name = _("i18next interpolation")
    description = _("The i18next interpolation does not match source")
    regexp = I18NEXT_MATCH

    def cleanup_string(self, text):
        return WHITESPACE.sub("", text)


class PercentPlaceholdersCheck(BaseFormatCheck):
    check_id = "percent_placeholders"
    name = _("Percent placeholders")
    description = _("The percent placeholders do not match source")
    regexp = PERCENT_MATCH
