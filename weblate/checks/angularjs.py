# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
# Copyright © 2015 Philipp Wolfer <ph.wolfer@gmail.com>
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
from django.utils.translation import ugettext_lazy as _
from weblate.checks.base import TargetCheck

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
    """Check for AngularJS interpolation string"""
    check_id = 'angularjs_format'
    name = _('AngularJS interpolation string')
    description = _('AngularJS interpolation strings do not match source')
    default_disabled = True
    severity = 'danger'

    def check_single(self, source, target, unit):
        src_match = ANGULARJS_INTERPOLATION_MATCH.findall(source)

        # Any interpolation strings in source?
        if not src_match:
            return False

        tgt_match = ANGULARJS_INTERPOLATION_MATCH.findall(target)

        # Fail the check if the number of matches is different
        if len(src_match) != len(tgt_match):
            return True

        # Remove whitespace
        src_tags = {re.sub(WHITESPACE, '', x) for x in src_match}
        tgt_tags = {re.sub(WHITESPACE, '', x) for x in tgt_match}

        return src_tags != tgt_tags

    def check_highlight(self, source, unit):
        if self.should_skip(unit):
            return []
        ret = []
        match_objects = ANGULARJS_INTERPOLATION_MATCH.finditer(source)
        for match in match_objects:
            ret.append((match.start(), match.end(), match.group()))
        return ret
