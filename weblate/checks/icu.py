# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.utils.translation import gettext, gettext_lazy
from pyicumessageformat import Parser

from weblate.checks.base import SourceCheck
from weblate.checks.format import BaseFormatCheck
from weblate.utils.html import format_html_join_comma, list_to_tuples

if TYPE_CHECKING:
    from weblate.trans.models import Unit

# Unique value for checking tags. Since types are
# always strings, this will never be encountered.
TAG_TYPE = -100

# These types are to be considered numeric. Numeric placeholders
# can be of any numeric type without triggering a warning from
# the checker.
NUMERIC_TYPES = ["number", "plural", "selectordinal"]

# These types have their sub-messages checked to ensure that
# sub-message selectors are valid.
PLURAL_TYPES = ["plural", "selectordinal"]

# ... and these are the valid selectors, along with selectors
# for specific values, formatted such as: =0, =1, etc.
PLURAL_SELECTORS = ["zero", "one", "two", "few", "many", "other"]


# We construct two Parser instances, one for tags and one without.
# Both parsers are configured to allow spaces inside formats, to not
# require other (which we can do better ourselves), and to be
# permissive about what types can have sub-messages.
standard_parser = Parser(
    {
        "include_indices": True,
        "loose_submessages": True,
        "allow_format_spaces": True,
        "require_other": False,
        "allow_tags": False,
    }
)

tag_parser = Parser(
    {
        "include_indices": True,
        "loose_submessages": True,
        "allow_format_spaces": True,
        "require_other": False,
        "allow_tags": True,
        "strict_tags": False,
        "tag_type": TAG_TYPE,
    }
)


strict_tag_parser = Parser(
    {
        "include_indices": True,
        "loose_submessages": True,
        "allow_format_spaces": True,
        "require_other": False,
        "allow_tags": True,
        "strict_tags": True,
        "tag_type": TAG_TYPE,
    }
)


def parse_icu(
    source: str,
    allow_tags: bool,
    strict_tags: bool,
    tag_prefix: str | None = None,
    want_tokens=False,
) -> tuple[list[str] | None, Exception | None, list[str] | None]:
    """Parse an ICU MessageFormat message."""
    ast = None
    err: Exception | None = None
    tokens: list[str] | None = [] if want_tokens else None
    parser = standard_parser
    if allow_tags:
        parser = strict_tag_parser if strict_tags else tag_parser

    parser.options["tag_prefix"] = tag_prefix

    try:
        ast = parser.parse(source, tokens)
    except SyntaxError as e:
        err = e

    parser.options["tag_prefix"] = None

    return ast, err, tokens


def check_bad_plural_selector(selector):
    if selector in PLURAL_SELECTORS:
        return False
    return selector[0] != "="


def update_maybe_value(value, old):
    """
    Certain placeholder values can have one of four values.

    `None`, `True`, `False`, or `0`.

    `None` represents a value never set.
    `True` or `False` represents a value selection.
    `0` represents a set value with conflicting values.

    This is useful if there are multiple placeholders with
    conflicting type info.
    """
    if old is None or old == value:
        return value
    return 0


def extract_highlights(token, source: str):
    """Extract all placeholders from an AST selected for highlighting."""
    if isinstance(token, str):
        return

    if isinstance(token, list):
        for tok in token:
            yield from extract_highlights(tok, source)

    # Sanity check the token. They should always have
    # start and end.
    if "start" not in token or "end" not in token:
        return

    start = token["start"]
    end = token["end"]
    usable = start < len(source)

    if token.get("hash"):
        usable = False

    if "options" in token:
        usable = False
        for subast in token["options"].values():
            yield from extract_highlights(subast, source)

    if "contents" in token:
        usable = False
        yield from extract_highlights(token["contents"], source)

    if usable:
        yield (start, end, source[start:end])


def extract_placeholders(token, variables=None):
    """Extract all placeholders from an AST and summarize their types."""
    if variables is None:
        variables = {}

    if isinstance(token, str):
        # Skip strings. Those aren't interesting.
        return variables

    if isinstance(token, list):
        # If we have a list, then we have a list of tokens so iterate
        # over the entire list.
        for tok in token:
            extract_placeholders(tok, variables)

        return variables

    if "name" not in token:
        # There should always be a name. This is highly suspicious.
        # Should this raise an exception?
        return variables

    name = token["name"]
    ttype = token.get("type")
    data = variables.setdefault(
        name,
        {
            "name": name,
            "types": set(),
            "formats": set(),
            "is_number": None,
            "is_tag": None,
            "is_empty": None,
        },
    )

    if ttype:
        is_tag = ttype is TAG_TYPE
        data["is_tag"] = update_maybe_value(is_tag, data["is_tag"])

        if is_tag:
            data["is_empty"] = update_maybe_value(
                "contents" not in token or not token["contents"], data["is_empty"]
            )
        else:
            data["types"].add(ttype)
            data["is_number"] = update_maybe_value(
                ttype in NUMERIC_TYPES, data["is_number"]
            )
            if "format" in token:
                data["formats"].add(token["format"])

    if "options" in token:
        choices = data.setdefault("choices", set())

        # We need to do three things with options:
        for selector, subast in token["options"].items():
            # First, we log the selector for later comparison.
            choices.add(selector)

            # Second, we ensure the selector is valid if we're working
            # with a plural/selectordinal type.
            if ttype in PLURAL_TYPES and check_bad_plural_selector(selector):
                data.setdefault("bad_plural", set()).add(selector)

            # Finally, we process the sub-ast for this option.
            extract_placeholders(subast, variables)

    # Make sure we process the contents sub-ast if one exists.
    if "contents" in token:
        extract_placeholders(token["contents"], variables)

    return variables


class ICUCheckMixin:
    def get_flags(self, unit: Unit):
        if unit and unit.all_flags.has_value("icu-flags"):
            return unit.all_flags.get_value("icu-flags")
        return []

    def get_tag_prefix(self, unit: Unit):
        if unit and unit.all_flags.has_value("icu-tag-prefix"):
            return unit.all_flags.get_value("icu-tag-prefix")
        return None


class ICUSourceCheck(ICUCheckMixin, SourceCheck):
    """Check for ICU MessageFormat syntax."""

    check_id = "icu_message_format_syntax"
    name = gettext_lazy("ICU MessageFormat syntax")
    description = gettext_lazy("Syntax errors in ICU MessageFormat strings.")
    default_disabled = True

    def __init__(self) -> None:
        super().__init__()
        self.enable_string = "icu-message-format"
        self.ignore_string = f"ignore-{self.enable_string}"

    def check_source_unit(self, sources: list[str], unit: Unit) -> bool:
        """Checker for source strings. Only check for syntax issues."""
        if not sources or not sources[0]:
            return False

        flags = self.get_flags(unit)
        strict_tags = "strict-xml" in flags
        allow_tags = strict_tags or "xml" in flags
        tag_prefix = self.get_tag_prefix(unit)

        _ast, src_err, _tokens = parse_icu(
            sources[0], allow_tags, strict_tags, tag_prefix
        )
        return bool(src_err)


class ICUMessageFormatCheck(ICUCheckMixin, BaseFormatCheck):
    """Check for ICU MessageFormat string."""

    check_id = "icu_message_format"
    name = gettext_lazy("ICU MessageFormat")
    description = gettext_lazy(
        "Syntax errors and/or placeholder mismatches in ICU MessageFormat strings."
    )

    def check_format(self, source: str, target: str, ignore_missing, unit: Unit):
        """Checker for ICU MessageFormat strings."""
        if not target or not source:
            return False

        flags = self.get_flags(unit)
        strict_tags = "strict-xml" in flags
        allow_tags = strict_tags or "xml" in flags
        tag_prefix = self.get_tag_prefix(unit)

        result = defaultdict(list)
        src_ast, src_err, _tokens = parse_icu(
            source, allow_tags, strict_tags, tag_prefix
        )

        # Check to see if we're running on a source string only.
        # If we are, then we can only run a syntax check on the
        # source and be done.
        if unit and unit.is_source:
            if src_err:
                result["syntax"].append(src_err)
                return result
            return False

        tgt_ast, tgt_err, _tokens = parse_icu(
            target, allow_tags, strict_tags, tag_prefix
        )
        if tgt_err:
            result["syntax"].append(tgt_err)

        if tgt_err:
            return result
        if src_err:
            # We cannot run any further checks if the source
            # string isn't valid, so just accept that the target
            # string is valid for now.
            return False

        # Both strings are valid! Congratulations. Let's extract
        # information on all the placeholders in both strings, and
        # compare them to see if anything is wrong.
        src_vars = extract_placeholders(src_ast)
        tgt_vars = extract_placeholders(tgt_ast)

        # First, we check all the variables in the target.
        for name, data in tgt_vars.items():
            self.check_for_other(result, name, data, flags)

            if name in src_vars:
                src_data = src_vars[name]

                self.check_bad_plural(result, name, data, src_data, flags)
                self.check_bad_submessage(result, name, data, src_data, flags)
                self.check_wrong_type(result, name, data, src_data, flags)

                if allow_tags:
                    self.check_tags(result, name, data, src_data, flags)

            else:
                self.check_bad_submessage(result, name, data, None, flags)

                # The variable does not exist in the source,
                # which suggests a mistake.
                if "-extra" not in flags:
                    result["extra"].append(name)

        # We also want to check for variables used in the
        # source but not in the target.
        self.check_missing(result, src_vars, tgt_vars, flags)

        if result:
            return result
        return False

    def check_missing(self, result, src_vars, tgt_vars, flags) -> None:
        """Detect any variables in the target not in the source."""
        if "-missing" in flags:
            return

        missing = [name for name in src_vars if name not in tgt_vars]

        if missing:
            result["missing"] = missing

    def check_for_other(self, result, name, data, flags) -> None:
        """Ensure types with sub-messages have other."""
        if "-require_other" in flags:
            return

        choices = data.get("choices")
        if choices and "other" not in choices:
            result["no_other"].append(name)

    def check_bad_plural(self, result, name, data, src_data, flags) -> None:
        """Forward bad plural selectors detected during extraction."""
        if "-plural_selectors" in flags:
            return

        if "bad_plural" in data:
            result["bad_plural"].append([name, data["bad_plural"]])

    def check_bad_submessage(self, result, name, data, src_data, flags) -> None:
        """Detect any bad sub-message selectors."""
        if "-submessage_selectors" in flags:
            return

        bad = set()

        # We also want to check individual select choices.
        if (
            src_data
            and "select" in data["types"]
            and "select" in src_data["types"]
            and "choices" in data
            and "choices" in src_data
        ):
            choices = data["choices"]
            src_choices = src_data["choices"]

            for selector in choices:
                if selector not in src_choices:
                    bad.add(selector)

        if bad:
            result["bad_submessage"].append([name, bad])

    def check_wrong_type(self, result, name, data, src_data, flags) -> None:
        """Ensure that types match, when possible."""
        if "-types" in flags:
            return

        # If we're dealing with a number, we want to use
        # special number logic, since numbers work with
        # multiple types.
        if isinstance(src_data["is_number"], bool) and src_data["is_number"]:
            if src_data["is_number"] != data["is_number"]:
                result["wrong_type"].append(name)

        else:
            for ttype in data["types"]:
                if ttype not in src_data["types"]:
                    result["wrong_type"].append(name)
                    break

    def check_tags(self, result, name, data, src_data, flags) -> None:
        """Correct any erroneous XML tags."""
        if "-tags" in flags:
            return

        if isinstance(src_data["is_tag"], bool) or data["is_tag"] is not None:
            if src_data["is_tag"]:
                if not data["is_tag"]:
                    result["should_be_tag"].append(name)

                elif (
                    isinstance(src_data["is_empty"], bool)
                    and src_data["is_empty"] != data["is_empty"]
                ):
                    if src_data["is_empty"]:
                        result["tag_not_empty"].append(name)
                    else:
                        result["tag_empty"].append(name)

            elif data["is_tag"]:
                result["not_tag"].append(name)

    def format_result(self, result):
        if result.get("syntax"):
            yield gettext("Syntax error: %s") % format_html_join_comma(
                "{}",
                list_to_tuples(err.msg or "unknown error" for err in result["syntax"]),
            )

        if result.get("extra"):
            yield gettext(
                "One or more unknown placeholders in the translation: %s"
            ) % format_html_join_comma("{}", list_to_tuples(result["extra"]))

        if result.get("missing"):
            yield gettext(
                "One or more placeholders missing in the translation: %s"
            ) % format_html_join_comma("{}", list_to_tuples(result["missing"]))

        if result.get("wrong_type"):
            yield gettext(
                "One or more placeholder types are incorrect: %s"
            ) % format_html_join_comma("{}", list_to_tuples(result["wrong_type"]))

        if result.get("no_other"):
            yield gettext("Missing other sub-message for: %s") % format_html_join_comma(
                "{}", list_to_tuples(result["no_other"])
            )

        if result.get("bad_plural"):
            yield gettext(
                "Incorrect plural selectors for: %s"
            ) % format_html_join_comma(
                "{}", (f"{x[0]} ({', '.join(x[1])})" for x in result["bad_plural"])
            )

        if result.get("bad_submessage"):
            yield gettext(
                "Incorrect sub-message selectors for: %s"
            ) % format_html_join_comma(
                "{}", (f"{x[0]} ({', '.join(x[1])})" for x in result["bad_submessage"])
            )

        if result.get("should_be_tag"):
            yield gettext(
                "One or more placeholders should have "
                "a corresponding XML tag in the translation: %s"
            ) % format_html_join_comma("{}", list_to_tuples(result["should_be_tag"]))

        if result.get("not_tag"):
            yield gettext(
                "One or more placeholders should not be "
                "an XML tag in the translation: %s"
            ) % format_html_join_comma("{}", list_to_tuples(result["not_tag"]))

        if result.get("tag_not_empty"):
            yield gettext(
                "One or more XML tags has unexpected content in the translation: %s"
            ) % format_html_join_comma("{}", list_to_tuples(result["tag_not_empty"]))

        if result.get("tag_empty"):
            yield gettext(
                "One or more XML tags missing content in the translation: %s"
            ) % format_html_join_comma("{}", list_to_tuples(result["tag_empty"]))

    def check_highlight(self, source: str, unit: Unit):
        if self.should_skip(unit):
            return

        flags = self.get_flags(unit)
        if "-highlight" in flags:
            return

        strict_tags = "strict-xml" in flags
        allow_tags = strict_tags or "xml" in flags
        tag_prefix = self.get_tag_prefix(unit)

        ast, _err, _tokens = parse_icu(
            source, allow_tags, strict_tags, tag_prefix, True
        )
        if not ast:
            return

        yield from extract_highlights(ast, source)
