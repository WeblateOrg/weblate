# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import Counter, defaultdict
from re import Pattern

from django.utils.functional import SimpleLazyObject
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext, gettext_lazy

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

SCHEME_PRINTF_MATCH = re.compile(
    r"""
    ~(                          # initial ~
        (?:(?P<ord>\d+)@\*~)?   # variable order, like ~1@*~d
        (?P<fullvar>
          (?:                   # any number of comma-separated parameters
            #([+-]?\d+|\'.|[vV]|#)
            ([+-]?\d+|'.|[vV]|\#)
            (, ([+-]?\d+|'.|[vV]|\#))*
          )?
          :?
          @?
          (?P<type>[a-zA-Z%\$\?&_/|!\[\]\(\)~]) # type (~a, ~s, etc.)
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

# index, width and precision can be '*', in which case their value
# will be read from the next element in the Args array
PASCAL_FORMAT_MATCH = re.compile(
    r"""
    %(                          # initial %
        (?:(?P<ord>\*|\d+):)?   # variable index, like %0:s
        (?P<fullvar>
            -?                  # left align
            (?:\*|\d+)?         # width
            (\.(?:\*|\d+))?     # precision
            (?P<type>[defgmnpsuxDEFGMNPSUX%]) # type (%s, %d, etc.)
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
            [-,?\s]+                    # flags
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
    r"""
    (
    %?{([^}]+)}
    |
# See https://github.com/kazupon/vue-i18n/blob/44ff0b9/src/index.js#L30
# but without case
    (?:@(?:\.[a-z]+)?:(?:[\w\-_|./]+|\([\w\-_:|./]+\)))
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

WHITESPACE = re.compile(r"\s+")


def c_format_is_position_based(string):
    return "$" not in string and string != "%"


def pascal_format_is_position_based(string):
    return ":" not in string and string != "%"


def scheme_format_is_position_based(string):
    return "@*" not in string and string != "~"


def python_format_is_position_based(string):
    return "(" not in string and string != "%"


def name_format_is_position_based(string):
    return not string


FLAG_RULES = {
    "python-format": (PYTHON_PRINTF_MATCH, python_format_is_position_based),
    "php-format": (PHP_PRINTF_MATCH, c_format_is_position_based),
    "c-format": (C_PRINTF_MATCH, c_format_is_position_based),
    "object-pascal-format": (PASCAL_FORMAT_MATCH, pascal_format_is_position_based),
    "perl-format": (C_PRINTF_MATCH, c_format_is_position_based),
    "javascript-format": (C_PRINTF_MATCH, c_format_is_position_based),
    "lua-format": (C_PRINTF_MATCH, c_format_is_position_based),
    "python-brace-format": (PYTHON_BRACE_MATCH, name_format_is_position_based),
    "scheme-format": (SCHEME_PRINTF_MATCH, scheme_format_is_position_based),
    "c-sharp-format": (C_SHARP_MATCH, name_format_is_position_based),
    "java-printf-format": (JAVA_MATCH, c_format_is_position_based),
}


class BaseFormatCheck(TargetCheck):
    """Base class for format string checks."""

    regexp: Pattern[str] | None = None
    plural_parameter_regexp: Pattern[str] | None = None
    default_disabled = True
    normalize_remove = None

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
            and self.regexp
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
            # won't be 0 so don't trigger too many false positives.
            # Some formats do strict linting here, so be strict on those as well.
            len(sources) > 1
            and "strict-format" not in unit.all_flags
            and (
                len(plural_examples[0]) == 1
                or (
                    plural_examples[0] == ["0", "1"]
                    and not unit.translation.component.file_format_cls.strict_format_plurals
                )
            ),
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
        if self.normalize_remove is None:
            return matches
        if isinstance(matches, Counter):
            matches.pop(self.normalize_remove, None)
            return matches
        return [m for m in matches if m != self.normalize_remove]

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
            src_matches = Counter(src_matches)
            tgt_matches = Counter(tgt_matches)

        if src_matches != tgt_matches:
            # Ignore mismatch in percent position
            if self.normalize(src_matches) == self.normalize(tgt_matches):
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
            # We can ignore missing format strings
            # for first of plurals
            if ignore_missing and missing and not extra:
                return False
            return {"missing": missing, "extra": extra}
        return False

    def is_position_based(self, string):
        return False

    def check_single(self, source, target, unit):
        """Target strings are checked in check_target_unit."""
        return False

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return
        match_objects = self.regexp.finditer(source)
        for match in match_objects:
            yield (match.start(), match.end(), match.group())

    def format_result(self, result):
        if (
            result["missing"]
            and all(self.is_position_based(flag) for flag in result["missing"])
            and set(result["missing"]) == set(result["extra"])
        ):
            yield gettext(
                "The following format strings are in the wrong order: %s"
            ) % ", ".join(self.format_string(x) for x in sorted(set(result["missing"])))
        else:
            if result["missing"]:
                yield self.get_missing_text(
                    self.format_string(x) for x in set(result["missing"])
                )
            if result["extra"]:
                yield self.get_extra_text(
                    self.format_string(x) for x in set(result["extra"])
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
            return format_html_join(
                format_html("<br />"), "{}", ((error,) for error in errors)
            )
        return super().get_description(check_obj)

    def interpolate_number(self, text: str, number: int) -> str:
        """
        Interpolates a count in the format strings.

        Attempt to find, in `text`, the placeholder for the number that controls
        which plural form is used, and replace it with `number`.

        Returns an empty string if the interpolation fails for any reason.
        """
        if not self.plural_parameter_regexp:
            # Interpolation isn't available for this format.
            raise ValueError("Unsupported interpolation!")
        it = self.plural_parameter_regexp.finditer(text)
        match = next(it, None)
        if not match:
            return text
        if next(it, None):
            # We've found two matching placeholders. We have no way to
            # determine which one we should replace, so we give up.
            return text
        return text[: match.start()] + str(number) + text[match.end() :]


class BasePrintfCheck(BaseFormatCheck):
    """Base class for printf based format checks."""

    normalize_remove = "%"

    def __init__(self):
        super().__init__()
        self.regexp, self._is_position_based = FLAG_RULES[self.enable_string]

    def is_position_based(self, string):
        return self._is_position_based(string)

    def format_string(self, string):
        return f"%{string}"

    def cleanup_string(self, text):
        """Remove locale-specific code from format string."""
        if "'" in text:
            return text.replace("'", "")
        return text


class PythonFormatCheck(BasePrintfCheck):
    """Check for Python format string."""

    check_id = "python_format"
    name = gettext_lazy("Python format")
    description = gettext_lazy("Python format string does not match source")
    plural_parameter_regexp = re.compile(r"%\((?:count|number|num|n)\)[a-zA-Z]")


class PHPFormatCheck(BasePrintfCheck):
    """Check for PHP format string."""

    check_id = "php_format"
    name = gettext_lazy("PHP format")
    description = gettext_lazy("PHP format string does not match source")


class CFormatCheck(BasePrintfCheck):
    """Check for C format string."""

    check_id = "c_format"
    name = gettext_lazy("C format")
    description = gettext_lazy("C format string does not match source")


class PerlFormatCheck(CFormatCheck):
    """Check for Perl format string."""

    check_id = "perl_format"
    name = gettext_lazy("Perl format")
    description = gettext_lazy("Perl format string does not match source")


class JavaScriptFormatCheck(CFormatCheck):
    """Check for JavaScript format string."""

    check_id = "javascript_format"
    name = gettext_lazy("JavaScript format")
    description = gettext_lazy("JavaScript format string does not match source")


class LuaFormatCheck(BasePrintfCheck):
    """Check for Lua format string."""

    check_id = "lua_format"
    name = gettext_lazy("Lua format")
    description = gettext_lazy("Lua format string does not match source")


class ObjectPascalFormatCheck(BasePrintfCheck):
    """Check for Object Pascal format string."""

    check_id = "object_pascal_format"
    name = gettext_lazy("Object Pascal format")
    description = gettext_lazy("Object Pascal format string does not match source")
    regexp = PASCAL_FORMAT_MATCH


class SchemeFormatCheck(BasePrintfCheck):
    """Check for Scheme format string."""

    check_id = "scheme_format"
    name = gettext_lazy("Scheme format")
    description = gettext_lazy("Scheme format string does not match source")
    normalize_remove = "~"

    def format_string(self, string):
        return f"~{string}"


class PythonBraceFormatCheck(BaseFormatCheck):
    """Check for Python format string."""

    check_id = "python_brace_format"
    name = gettext_lazy("Python brace format")
    description = gettext_lazy("Python brace format string does not match source")
    regexp = PYTHON_BRACE_MATCH
    plural_parameter_regexp = re.compile(r"\{(?:count|number|num|n)\}")

    def is_position_based(self, string):
        return name_format_is_position_based(string)

    def format_string(self, string):
        return "{%s}" % string


class CSharpFormatCheck(BaseFormatCheck):
    """Check for C# format string."""

    check_id = "c_sharp_format"
    name = gettext_lazy("C# format")
    description = gettext_lazy("C# format string does not match source")
    regexp = C_SHARP_MATCH

    def is_position_based(self, string):
        return name_format_is_position_based(string)

    def format_string(self, string):
        return "{%s}" % string


class JavaFormatCheck(BasePrintfCheck):
    """Check for Java format string."""

    check_id = "java_printf_format"
    name = gettext_lazy("Java format")
    description = gettext_lazy("Java format string does not match source")


class JavaMessageFormatCheck(BaseFormatCheck):
    """Check for Java MessageFormat string."""

    check_id = "java_format"
    name = gettext_lazy("Java MessageFormat")
    description = gettext_lazy("Java MessageFormat string does not match source")
    regexp = JAVA_MESSAGE_MATCH

    def format_string(self, string):
        return "{%s}" % string

    def should_skip(self, unit):
        all_flags = unit.all_flags
        if self.is_ignored(all_flags):
            return True

        if "auto-java-messageformat" in unit.all_flags and "{0" in unit.source:
            return False

        return super().should_skip(unit)

    def check_format(self, source, target, ignore_missing, unit):
        """Generic checker for format strings."""
        if not target or not source:
            return False

        result = super().check_format(source, target, ignore_missing, unit)

        # Even number of quotes, unless in GWT which enforces this
        if (
            unit.translation.component.file_format != "gwt"
            and target.count("'") % 2 != 0
        ):
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
    name = gettext_lazy("i18next interpolation")
    description = gettext_lazy("The i18next interpolation does not match source")
    regexp = I18NEXT_MATCH
    # https://www.i18next.com/translation-function/plurals
    plural_parameter_regexp = re.compile(r"{{count}}")

    def cleanup_string(self, text):
        return WHITESPACE.sub("", text)


class ESTemplateLiteralsCheck(BaseFormatCheck):
    """Check for ES template literals."""

    check_id = "es_format"
    name = gettext_lazy("ECMAScript template literals")
    description = gettext_lazy("ECMAScript template literals do not match source")
    regexp = ES_TEMPLATE_MATCH
    plural_parameter_regexp = re.compile(r"\$\{(?:count|number|num|n)\}")

    def cleanup_string(self, text):
        return WHITESPACE.sub("", text)

    def format_string(self, string):
        return f"${{{string}}}"


class PercentPlaceholdersCheck(BaseFormatCheck):
    check_id = "percent_placeholders"
    name = gettext_lazy("Percent placeholders")
    description = gettext_lazy("The percent placeholders do not match source")
    regexp = PERCENT_MATCH
    plural_parameter_regexp = re.compile(r"%(?:count|number|num|n)%")


class VueFormattingCheck(BaseFormatCheck):
    check_id = "vue_format"
    name = gettext_lazy("Vue I18n formatting")
    description = gettext_lazy("The Vue I18n formatting does not match source")
    regexp = VUE_MATCH
    # https://kazupon.github.io/vue-i18n/guide/pluralization.html
    plural_parameter_regexp = re.compile(r"%?\{(?:count|n)\}")


class MultipleUnnamedFormatsCheck(SourceCheck):
    check_id = "unnamed_format"
    name = gettext_lazy("Multiple unnamed variables")
    description = gettext_lazy(
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
