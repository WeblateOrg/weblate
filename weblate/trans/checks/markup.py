# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.utils.translation import ugettext_lazy as _
from xml.etree import cElementTree
import re
from weblate.trans.checks.base import TargetCheck

BBCODE_MATCH = re.compile(
    r'\[(?P<tag>[^]]*)(?=(@[^]]*)?\](.*?)\[\/(?P=tag)\])',
    re.MULTILINE
)

XML_MATCH = re.compile(r'<[^>]+>')
XML_ENTITY_MATCH = re.compile(r'&#?\w+;')


def strip_entities(text):
    '''
    Strips all HTML entities (we don't care about them).
    '''
    return XML_ENTITY_MATCH.sub('', text)


class BBCodeCheck(TargetCheck):
    '''
    Check for matching bbcode tags.
    '''
    check_id = 'bbcode'
    name = _('Mismatched BBcode')
    description = _('BBcode in translation does not match source')
    severity = 'warning'

    def check_single(self, source, target, unit, cache_slot):
        # Try geting source parsing from cache
        src_match = self.get_cache(unit, cache_slot)
        # Cache miss
        if src_match is None:
            src_match = BBCODE_MATCH.findall(source)
            self.set_cache(unit, src_match, cache_slot)
        # Any BBCode in source?
        if len(src_match) == 0:
            return False
        # Parse target
        tgt_match = BBCODE_MATCH.findall(target)
        if len(src_match) != len(tgt_match):
            return True

        src_tags = set([x[0] for x in src_match])
        tgt_tags = set([x[0] for x in tgt_match])

        return src_tags != tgt_tags


class XMLTagsCheck(TargetCheck):
    '''
    Check whether XML in target matches source.
    '''
    check_id = 'xml-tags'
    name = _('XML tags mismatch')
    description = _('XML tags in translation do not match source')
    severity = 'warning'

    def parse_xml(self, text):
        '''
        Wrapper for parsing XML.
        '''
        text = strip_entities(text.encode('utf-8'))
        return cElementTree.fromstring('<weblate>%s</weblate>' % text)

    def check_single(self, source, target, unit, cache_slot):
        # Try getting source string data from cache
        source_tags = self.get_cache(unit, cache_slot)

        # Source is not XML
        if source_tags == []:
            return False

        # Do we need to process source (cache miss)
        if source_tags is None:
            # Quick check if source looks like XML
            if '<' not in source or len(XML_MATCH.findall(source)) == 0:
                self.set_cache(unit, [], cache_slot)
                return False
            # Check if source is XML
            try:
                source_tree = self.parse_xml(source)
                source_tags = [x.tag for x in source_tree]
                self.set_cache(unit, source_tags, cache_slot)
            except SyntaxError:
                # Source is not valid XML, we give up
                self.set_cache(unit, [], cache_slot)
                return False

        # Check target
        try:
            target_tree = self.parse_xml(target)
            target_tags = [x.tag for x in target_tree]
        except SyntaxError:
            # Target is not valid XML
            return True

        # Compare tags
        return source_tags != target_tags
