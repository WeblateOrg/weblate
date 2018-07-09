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

from __future__ import unicode_literals

import re

from defusedxml import lxml

from django.utils.translation import ugettext_lazy as _

from weblate.checks.base import TargetCheck

BBCODE_MATCH = re.compile(
    r'(?P<start>\[(?P<tag>[^]]+)(@[^]]*)?\])(.*?)(?P<end>\[\/(?P=tag)\])',
    re.MULTILINE
)

XML_MATCH = re.compile(r'<[^>]+>')
XML_ENTITY_MATCH = re.compile(r'&#?\w+;')


def strip_entities(text):
    """Strip all HTML entities (we don't care about them)."""
    return XML_ENTITY_MATCH.sub('', text)


class BBCodeCheck(TargetCheck):
    """Check for matching bbcode tags."""
    check_id = 'bbcode'
    name = _('Mismatched BBcode')
    description = _('BBcode in translation does not match source')
    severity = 'warning'

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
            return []
        ret = []
        for match in BBCODE_MATCH.finditer(source):
            for tag in ('start', 'end'):
                ret.append((
                    match.start(tag),
                    match.end(tag),
                    match.group(tag)
                ))
        return ret


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
            text = '<weblate>{}</weblate>'.format(text)

        return lxml.fromstring(text.encode('utf-8'))

    def is_source_xml(self, flags, source):
        """Quick check if source looks like XML."""
        if 'xml-text' in flags:
            return True
        return '<' in source and len(XML_MATCH.findall(source))

    def check_single(self, source, target, unit):
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError()


class XMLValidityCheck(BaseXMLCheck):
    """Check whether XML in target is valid."""
    check_id = 'xml-invalid'
    name = _('Invalid XML markup')
    description = _('The translation is not valid XML')
    severity = 'danger'

    def check_single(self, source, target, unit):
        if not self.is_source_xml(unit.all_flags, source):
            return False

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
    check_id = 'xml-tags'
    name = _('XML tags mismatch')
    description = _('XML tags in translation do not match source')
    severity = 'warning'

    def check_single(self, source, target, unit):
        if not self.is_source_xml(unit.all_flags, source):
            return False

        # Check if source is XML
        try:
            source_tree, wrap = self.parse_xml(source)
            source_tags = [x.tag for x in source_tree.iter()]
        except SyntaxError:
            # Source is not valid XML, we give up
            return False

        # Check target
        try:
            target_tree = self.parse_xml(target, wrap)
            target_tags = [x.tag for x in target_tree.iter()]
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
        for match in XML_MATCH.finditer(source):
            ret.append((match.start(), match.end(), match.group()))
        for match in XML_ENTITY_MATCH.finditer(source):
            ret.append((match.start(), match.end(), match.group()))
        return ret
