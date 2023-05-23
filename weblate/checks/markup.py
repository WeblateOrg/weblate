#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

import bleach
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheck
from weblate.utils.html import extract_bleach
from weblate.utils.xml import parse_xml

BBCODE_MATCH = re.compile(
    r"(?P<start>\[(?P<tag>[^]]+)(@[^]]*)?\])(.*?)(?P<end>\[\/(?P=tag)\])", re.MULTILINE
)

MD_LINK = re.compile(
    r"""
    (?:
    !?                                                          # Exclamation for images
    \[((?:\[[^^\]]*\]|[^\[\]]|\](?=[^\[]*\]))*)\]               # Link text
    \(
        \s*(<)?([\s\S]*?)(?(2)>)                                # URL
        (?:\s+['"]([\s\S]*?)['"])?\s*                           # Title
    \)
    |
    <(https?://[^>]+)>                                          # URL
    |
    <([^>]+@[^>]+\.[^>]+)>                                      # E-mail
    )
    """,
    re.VERBOSE,
)
MD_BROKEN_LINK = re.compile(r"\] +\(")
MD_REFLINK = re.compile(
    r"!?\[("  # leading [
    r"(?:\[[^^\]]*\]|[^\[\]]|\](?=[^\[]*\]))*"  # link text
    r")\]\s*\[([^^\]]*)\]"  # trailing ] with optional target
)
MD_SYNTAX = re.compile(
    r"""
    (_{2})(?:[\s\S]+?)_{2}(?!_)         # __word__
    |
    (\*{2})(?:[\s\S]+?)\*{2}(?!\*)      # **word**
    |
    \b(_)(?:(?:__|[^_])+?)_\b           # _word_
    |
    (\*)(?:(?:\*\*|[^\*])+?)\*(?!\*)    # *word*
    |
    (`+)\s*(?:[\s\S]*?[^`])\s*\5(?!`)   # `code`
    |
    (~~)(?=\S)(?:[\s\S]*?\S)~~          # ~~word~~
    |
    (<)(?:https?://[^>]+)>              # URL
    |
    (<)(?:[^>]+@[^>]+\.[^>]+)>          # E-mail
    """,
    re.VERBOSE,
)
MD_SYNTAX_GROUPS = 8

XML_MATCH = re.compile(r"<[^>]+>")
XML_ENTITY_MATCH = re.compile(r"&#?\w+;")


def strip_entities(text):
    """Strip all HTML entities (we don't care about them)."""
    return XML_ENTITY_MATCH.sub(" ", text)


class BBCodeCheck(TargetCheck):
    """Check for matching bbcode tags."""

    check_id = "bbcode"
    name = _("BBCode markup")
    description = _("BBCode in translation does not match source")

    def check_single(self, source, target, unit):
        # Parse source
        src_match = BBCODE_MATCH.findall(source)
        # Any BBCode in source?
        if not src_match:
            return False
        # Parse target
        tgt_match = BBCODE_MATCH.findall(target)
        if len(src_match) != len(tgt_match):
            return True

        src_tags = {x[1] for x in src_match}
        tgt_tags = {x[1] for x in tgt_match}

        return src_tags != tgt_tags

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return
        for match in BBCODE_MATCH.finditer(source):
            for tag in ("start", "end"):
                yield match.start(tag), match.end(tag), match.group(tag)


class BaseXMLCheck(TargetCheck):
    def parse_xml(self, text, wrap=None):
        """Wrapper for parsing XML."""
        if wrap is None:
            # Detect whether wrapping is desired
            try:
                return self.parse_xml(text, True), True
            except SyntaxError:
                return self.parse_xml(text, False), False
        text = strip_entities(text)
        if wrap:
            text = f"<weblate>{text}</weblate>"

        return parse_xml(text.encode() if "encoding" in text else text)

    def should_skip(self, unit):
        result = super().should_skip(unit)
        if result:
            return True

        flags = unit.all_flags

        if "safe-html" in flags:
            return True

        if "xml-text" in flags:
            return False

        # Quick check if source looks like XML.
        return not any(
            "<" in source and len(XML_MATCH.findall(source))
            for source in unit.get_source_plurals()
        )

    def check_single(self, source, target, unit):
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError()


class XMLValidityCheck(BaseXMLCheck):
    """Check whether XML in target is valid."""

    check_id = "xml-invalid"
    name = _("XML syntax")
    description = _("The translation is not valid XML")

    def check_single(self, source, target, unit):
        # Check if source is XML
        try:
            wrap = self.parse_xml(source)[1]
        except SyntaxError:
            # Source is not valid XML, we give up
            return False

        # Check target
        try:
            self.parse_xml(target, wrap)
        except SyntaxError:
            # Target is not valid XML
            return True

        return False


class XMLTagsCheck(BaseXMLCheck):
    """Check whether XML in target matches source."""

    check_id = "xml-tags"
    name = _("XML markup")
    description = _("XML tags in translation do not match source")

    def check_single(self, source, target, unit):
        # Check if source is XML
        try:
            source_tree, wrap = self.parse_xml(source)
            source_tags = [(x.tag, x.keys()) for x in source_tree.iter()]
        except SyntaxError:
            # Source is not valid XML, we give up
            return False

        # Check target
        try:
            target_tree = self.parse_xml(target, wrap)
            target_tags = [(x.tag, x.keys()) for x in target_tree.iter()]
        except SyntaxError:
            # Target is not valid XML
            return False

        # Compare tags
        return source_tags != target_tags

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return []
        ret = []
        try:
            self.parse_xml(source)
        except SyntaxError:
            return ret
        # Include XML markup
        for match in XML_MATCH.finditer(source):
            ret.append((match.start(), match.end(), match.group()))
        # Add XML entities
        skipranges = [x[:2] for x in ret]
        skipranges.append((len(source), len(source)))
        offset = 0
        for match in XML_ENTITY_MATCH.finditer(source):
            start = match.start()
            end = match.end()
            while skipranges[offset][1] < end:
                offset += 1
            # Avoid including entities inside markup
            if start > skipranges[offset][0] and end < skipranges[offset][1]:
                continue
            ret.append((start, end, match.group()))
        return ret


class MarkdownBaseCheck(TargetCheck):
    default_disabled = True

    def __init__(self):
        super().__init__()
        self.enable_string = "md-text"


class MarkdownRefLinkCheck(MarkdownBaseCheck):
    check_id = "md-reflink"
    name = _("Markdown references")
    description = _("Markdown link references do not match source")

    def check_single(self, source, target, unit):
        src_match = MD_REFLINK.findall(source)
        if not src_match:
            return False
        tgt_match = MD_REFLINK.findall(target)

        src_tags = {x[1] for x in src_match}
        tgt_tags = {x[1] for x in tgt_match}

        return src_tags != tgt_tags


class MarkdownLinkCheck(MarkdownBaseCheck):
    check_id = "md-link"
    name = _("Markdown links")
    description = _("Markdown links do not match source")

    def check_single(self, source, target, unit):
        src_match = MD_LINK.findall(source)
        if not src_match:
            return False
        tgt_match = MD_LINK.findall(target)

        # Check number of links
        if len(src_match) != len(tgt_match):
            return True

        # We don't check actual remote link targets as those might
        # be localized as well (consider links to Wikipedia).
        # Instead we check only relative links and templated ones.
        link_start = (".", "#", "{")
        tgt_anchors = {x[2] for x in tgt_match if x[2] and x[2][0] in link_start}
        src_anchors = {x[2] for x in src_match if x[2] and x[2][0] in link_start}
        return tgt_anchors != src_anchors

    def get_fixup(self, unit):
        if MD_BROKEN_LINK.findall(unit.target):
            return [(MD_BROKEN_LINK.pattern, "](")]
        return None


class MarkdownSyntaxCheck(MarkdownBaseCheck):
    check_id = "md-syntax"
    name = _("Markdown syntax")
    description = _("Markdown syntax does not match source")

    @staticmethod
    def extract_match(match):
        for i in range(6):
            if match[i]:
                return match[i]
        return None

    def check_single(self, source, target, unit):
        src_tags = {self.extract_match(x) for x in MD_SYNTAX.findall(source)}
        tgt_tags = {self.extract_match(x) for x in MD_SYNTAX.findall(target)}

        return src_tags != tgt_tags

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return
        for match in MD_SYNTAX.finditer(source):
            value = ""
            for i in range(MD_SYNTAX_GROUPS):
                value = match.group(i + 1)
                if value:
                    break
            start = match.start()
            end = match.end()
            yield (start, start + len(value), value)
            yield ((end - len(value), end, value if value != "<" else ">"))


class URLCheck(TargetCheck):
    check_id = "url"
    name = _("URL")
    description = _("The translation does not contain an URL")
    default_disabled = True

    @cached_property
    def validator(self):
        return URLValidator()

    def check_single(self, source, target, unit):
        if not source:
            return False
        try:
            self.validator(target)
            return False
        except ValidationError:
            return True


class SafeHTMLCheck(TargetCheck):
    check_id = "safe-html"
    name = _("Unsafe HTML")
    description = _("The translation uses unsafe HTML markup")
    default_disabled = True

    def check_single(self, source, target, unit):

        # Strip MarkDown links
        if "md-text" in unit.all_flags:
            target = MD_LINK.sub("", target)

        return bleach.clean(target, **extract_bleach(source)) != target
