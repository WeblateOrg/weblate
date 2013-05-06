# -*- coding: utf-8 -*-
import re

from base import AutoFix


class SameBookendingWhitespace(AutoFix):

    def bookend_whitespace(self, target):
        '''
        Help non-techy translators with their whitespace
        '''

        # normalize newlines of source
        source = re.compile(r'\r\n|\r|\n').sub('\n', self.source)

        #capture preceding and tailing whitespace
        start = re.compile(r'^(\s+)').search(source)
        end = re.compile(r'(\s+)$').search(source)
        head = start.group() if start else ''
        tail = end.group() if end else ''

        # add the whitespace around the target translation (ignore blanks)
        stripped = target.strip()
        if stripped:
            target = '%s%s%s' % (head, stripped, tail)
        return target

    def fix_target(self, single_target):
        return self.bookend_whitespace(single_target)
