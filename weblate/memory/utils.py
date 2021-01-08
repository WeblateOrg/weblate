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

CATEGORY_FILE = 1
CATEGORY_SHARED = 2
CATEGORY_PRIVATE_OFFSET = 10000000
CATEGORY_USER_OFFSET = 20000000


def parse_category(category):
    """
    Parse category field.

    Returns tuple with from_file, shared, project_id, user_id.
    """
    if category == CATEGORY_FILE:
        return True, False, None, None
    if category == CATEGORY_SHARED:
        return False, True, None, None
    if CATEGORY_PRIVATE_OFFSET <= category < CATEGORY_USER_OFFSET:
        return False, False, category - CATEGORY_PRIVATE_OFFSET, None
    return False, False, None, category - CATEGORY_USER_OFFSET
