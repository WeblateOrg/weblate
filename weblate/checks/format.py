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
from collections import defaultdict
from typing import Optional, Pattern

from django.utils.functional import SimpleLazyObject
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import SourceCheck, TargetCheck

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

ES_TEMPLATE_MATCH = re.compile(
    r"""
    \${             # start symbol
        \s*         # ignore whitespace
        (([^}]+))   # variable name
        \s*         # ignore whitespace
    }               # end symbol
    """,
    re.VERBOSE,
)


PERCENT_MATCH = re.compile(r"(%([a-zA-Z0-9_]+)%)")

VUE_MATCH = re.compile(
    r"(%?{([^}]+)}|@(?:\.[a-z]+)?:(?:\([^)]+\)|[a-z_.]+))", re.IGNORECASE
)

WHITESPACE = re.compile(r"\s+")


def c_format_is_position_based(string):
    return "$" not in string and string != "%"


def python_format_is_position_based(string):
    return "(" not in string and string != "%"


def name_format_is_position_based(string):
    return string == ""


FLAG_RULES = {
    "python-format": (PYTHON_PRINTF_MATCH, python_format_is_position_based),
    "php-format": (PHP_PRINTF_MATCH, c_format_is_position_based),
    "c-format": (C_PRINTF_MATCH, c_format_is_position_based),
    "perl-format": (C_PRINTF_MATCH, c_format_is_position_based),
    "javascript-format": (C_PRINTF_MATCH, c_format_is_position_based),
    "lua-format": (C_PRINTF_MATCH, c_format_is_position_based),
    "python-brace-format": (PYTHON_BRACE_MATCH, name_format_is_position_based),
    "c-sharp-format": (C_SHARP_MATCH, name_format_is_position_based),
    "java-format": (JAVA_MATCH, c_format_is_position_based),
}


class BaseFormatCheck(TargetCheck):
    """Base class for format string checks."""

    regexp: Optional[Pattern[str]] = None
    default_disabled = True

    def check_target_unit(self, sources, targets, unit):
        """Check single unit, handling plurals."""
        return any(self.check_generator(sources, targets, unit))

    def check_generator(self, sources, targets, unit):
        # Special case languages with single plural form
        if len(sources) > 1 and len(targets) == 1:
            yield self.check_format(sources[1], targets[0], False, unit)
            return

        # Use plural as source in case singular misses format string and plural has it
        if (
            len(sources) > 1
            and not self.extract_matches(sources[0])
            and self.extract_matches(sources[1])
        ):
            source = sources[1]
        else:
            source = sources[0]

        # Fetch plural examples
        plural_examples = SimpleLazyObject(lambda: unit.translation.plural.examples)

        # Check singular
        yield self.check_format(
            source,
            targets[0],
            # Allow to skip format string in case there is single plural or in special
            # case of 0, 1 plural. It is technically wrong, but in many cases there
            # won't be 0 so don't trigger too many false positives
            len(sources) > 1
            and (len(plural_examples[0]) == 1 or plural_examples[0] == ["0", "1"]),
            unit,
        )

        # Do we have more to check?
        if len(sources) == 1:
            return

        # Check plurals against plural from source
        for i, target in enumerate(targets[1:]):
            yield self.check_format(
                sources[1], target, len(plural_examples[i + 1]) == 1, unit
            )

    def format_string(self, string):
        return string

    def cleanup_string(self, text):
        return text

    def normalize(self, matches):
        return matches

    def extract_matches(self, string):
        return [self.cleanup_string(x[0]) for x in self.regexp.findall(string)]

    def check_format(self, source, target, ignore_missing, unit):
        """Generic checker for format strings."""
        if not target or not source:
            return False

        uses_position = True

        # Calculate value
        src_matches = self.extract_matches(source)
        if src_matches:
            uses_position = any(self.is_position_based(x) for x in src_matches)

        tgt_matches = self.extract_matches(target)

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
                missing = sorted(src_matches - tgt_matches)
                extra = sorted(tgt_matches - src_matches)
            else:
                missing = []
                extra = []
                for i in range(min(len(src_matches), len(tgt_matches))):
                    if src_matches[i] != tgt_matches[i]:
                        missing.append(src_matches[i])
                        extra.append(tgt_matches[i])
                missing.extend(src_matches[len(tgt_matches) :])
                extra.extend(tgt_matches[len(src_matches) :])
            return {"missing": missing, "extra": extra}
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
        if result["missing"]:
            yield gettext("Following format strings are missing: %s") % ", ".join(
                self.format_string(x) for x in sorted(set(result["missing"]))
            )
        if result["extra"]:
            yield gettext("Following format strings are extra: %s") % ", ".join(
                self.format_string(x) for x in sorted(set(result["extra"]))
            )

    def get_description(self, check_obj):
        unit = check_obj.unit
        checks = self.check_generator(
            unit.get_source_plurals(), unit.get_target_plurals(), unit
        )
        errors = []

        # Merge plurals
        results = defaultdict(list)
        for result in checks:
            if result:
                for key, value in result.items():
                    results[key].extend(value)
        if results:
            errors.extend(self.format_result(results))
        if errors:
            return mark_safe("<br />".join(escape(error) for error in errors))
        return super().get_description(check_obj)


class BasePrintfCheck(BaseFormatCheck):
    """Base class for printf based format checks."""

    def __init__(self):
        super().__init__()
        self.regexp, self._is_position_based = FLAG_RULES[self.enable_string]

    def is_position_based(self, string):
        return self._is_position_based(string)

    def normalize(self, matches):
        return [m for m in matches if m != "%"]

    def format_string(self, string):
        return f"%{string}"

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


class PHPFormatCheck(BasePrintfCheck):
    """Check for PHP format string."""

    check_id = "php_format"
    name = _("PHP format")
    description = _("PHP format string does not match source")


class CFormatCheck(BasePrintfCheck):
    """Check for C format string."""

    check_id = "c_format"
    name = _("C format")
    description = _("C format string does not match source")


class PerlFormatCheck(CFormatCheck):
    """Check for Perl format string."""

    check_id = "perl_format"
    name = _("Perl format")
    description = _("Perl format string does not match source")


class JavaScriptFormatCheck(CFormatCheck):
    """Check for JavaScript format string."""

    check_id = "javascript_format"
    name = _("JavaScript format")
    description = _("JavaScript format string does not match source")


class LuaFormatCheck(BasePrintfCheck):
    """Check for Lua format string."""

    check_id = "lua_format"
    name = _("Lua format")
    description = _("Lua format string does not match source")


class PythonBraceFormatCheck(BaseFormatCheck):
    """Check for Python format string."""

    check_id = "python_brace_format"
    name = _("Python brace format")
    description = _("Python brace format string does not match source")
    regexp = PYTHON_BRACE_MATCH

    def is_position_based(self, string):
        return name_format_is_position_based(string)

    def format_string(self, string):
        return "{%s}" % string


class CSharpFormatCheck(BaseFormatCheck):
    """Check for C# format string."""

    check_id = "c_sharp_format"
    name = _("C# format")
    description = _("C# format string does not match source")
    regexp = C_SHARP_MATCH

    def is_position_based(self, string):
        return name_format_is_position_based(string)

    def format_string(self, string):
        return "{%s}" % string


class JavaFormatCheck(BasePrintfCheck):
    """Check for Java format string."""

    check_id = "java_format"
    name = _("Java format")
    description = _("Java format string does not match source")


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

    def check_format(self, source, target, ignore_missing, unit):
        """Generic checker for format strings."""
        if not target or not source:
            return False

        result = super().check_format(source, target, ignore_missing, unit)

        # Even number of quotes, unless in GWT which enforces this
        if unit.translation.component.file_format != "gwt":
            if target.count("'") % 2 != 0:
                if not result:
                    result = {"missing": [], "extra": []}
                result["missing"].append("'")

        return result

    def format_result(self, result):
        if "'" in result["missing"]:
            result["missing"].remove("'")
            yield gettext("You need to pair up an apostrophe with another one.")
        yield from super().format_result(result)


class I18NextInterpolationCheck(BaseFormatCheck):
    check_id = "i18next_interpolation"
    name = _("i18next interpolation")
    description = _("The i18next interpolation does not match source")
    regexp = I18NEXT_MATCH

    def cleanup_string(self, text):
        return WHITESPACE.sub("", text)


class ESTemplateLiteralsCheck(BaseFormatCheck):
    """Check for ES template literals."""

    check_id = "es_format"
    name = _("ECMAScript template literals")
    description = _("ECMAScript template literals do not match source")
    regexp = ES_TEMPLATE_MATCH

    def cleanup_string(self, text):
        return WHITESPACE.sub("", text)

    def format_string(self, string):
        return f"${{{string}}}"


class PercentPlaceholdersCheck(BaseFormatCheck):
    check_id = "percent_placeholders"
    name = _("Percent placeholders")
    description = _("The percent placeholders do not match source")
    regexp = PERCENT_MATCH


class VueFormattingCheck(BaseFormatCheck):
    check_id = "vue_format"
    name = _("Vue I18n formatting")
    description = _("The Vue I18n formatting does not match source")
    regexp = VUE_MATCH


class MultipleUnnamedFormatsCheck(SourceCheck):
    check_id = "unnamed_format"
    name = _("Multiple unnamed variables")
    description = _(
        "There are multiple unnamed variables in the string, "
        "making it impossible for translators to reorder them"
    )

    def check_source_unit(self, source, unit):
        """Check source string."""
        rules = [FLAG_RULES[flag] for flag in unit.all_flags if flag in FLAG_RULES]
        if not rules:
            return False
        found = set()
        for regexp, is_position_based in rules:
            for match in regexp.finditer(source[0]):
                if is_position_based(match[1]):
                    found.add((match.start(0), match.end(0)))
                    if len(found) >= 2:
                        return True
        return False
