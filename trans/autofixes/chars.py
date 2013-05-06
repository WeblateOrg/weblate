# -*- coding: utf-8 -*-
import re

from base import AutoFix


class ReplaceTrailingDotsWithEllipsis(AutoFix):
    '''
    Replace Trailing Dots with an Ellipsis.
    Ignore and maintain exisiting trailing whitespace
    '''
    def fix_target(self, target):
        source_match = re.compile(u'…(\s*)$').search(self.source)
        re_dots = re.compile(u'\.\.\.(\s*)$')
        target_match = re_dots.search(target)
        if source_match and target_match:
            elip_whitespace = u'…' + target_match.group(1)
            target = re_dots.sub(elip_whitespace, target)
        return target
