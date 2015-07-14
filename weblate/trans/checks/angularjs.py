# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
# Copyright © 2015 Philipp Wolfer <ph.wolfer@gmail.com>
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

from weblate.trans.checks.base import TargetCheck
from django.utils.translation import ugettext_lazy as _
import re

ANGULARJS_INTERPOLATION_MATCH = re.compile(
    r'''
    {{              # start symbol
        \s*         # ignore whitespace
        (.+?)
        \s*         # ignore whitespace
    }}              # end symbol
    ''',
    re.VERBOSE
)

WHITESPACE = re.compile(r'\s+')


class AngularJSInterpolationCheck(TargetCheck):
    '''
    Check for AngularJS interpolation string
    '''
    check_id = 'angularjs_format'
    name = _('AngularJS interpolation string')
    description = _('AngularJS interpolation strings do not match source')
    severity = 'danger'
    flag = 'angularjs-format'

    def check_single(self, source, target, unit, cache_slot):
        # Verify unit is properly flagged
        if self.flag not in unit.all_flags:
            return False

        # Try geting source parsing from cache
        src_match = self.get_cache(unit, cache_slot)

        # Cache miss
        if src_match is None:
            src_match = ANGULARJS_INTERPOLATION_MATCH.findall(source)
            self.set_cache(unit, src_match, cache_slot)
        # Any interpolation strings in source?
        if len(src_match) == 0:
            return False
        # Parse target
        tgt_match = ANGULARJS_INTERPOLATION_MATCH.findall(target)
        if len(src_match) != len(tgt_match):
            return True

        # Remove whitespace
        src_tags = set([re.sub(WHITESPACE, '', x) for x in src_match])
        tgt_tags = set([re.sub(WHITESPACE, '', x) for x in tgt_match])

        return src_tags != tgt_tags
