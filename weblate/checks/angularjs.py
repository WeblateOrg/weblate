#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django.utils.translation import gettext_lazy as _

from .format import BaseFormatCheck

ANGULARJS_INTERPOLATION_MATCH = re.compile(
    r"""
    {{              # start symbol
        \s*         # ignore whitespace
        ((.+?))
        \s*         # ignore whitespace
    }}              # end symbol
    """,
    re.VERBOSE,
)

WHITESPACE = re.compile(r"\s+")


class AngularJSInterpolationCheck(BaseFormatCheck):
    """Check for AngularJS interpolation string."""

    check_id = "angularjs_format"
    name = _("AngularJS interpolation string")
    description = _("AngularJS interpolation strings do not match source")
    regexp = ANGULARJS_INTERPOLATION_MATCH

    def cleanup_string(self, text):
        return WHITESPACE.sub("", text)
