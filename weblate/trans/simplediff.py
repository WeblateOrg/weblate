#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from diff_match_patch import diff_match_patch
from django.utils.html import escape


def html_diff(old, new):
    """Generate HTML formatted diff of two strings."""
    dmp = diff_match_patch()
    diff = dmp.diff_main(old, new)
    dmp.diff_cleanupSemantic(diff)

    result = []
    for op, data in diff:
        if op == dmp.DIFF_DELETE:
            result.append("<del>{}</del>".format(escape(data)))
        elif op == dmp.DIFF_INSERT:
            result.append("<ins>{}</ins>".format(escape(data)))
        elif op == dmp.DIFF_EQUAL:
            result.append(escape(data))
    return "".join(result)
