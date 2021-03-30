#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


from siphashc import siphash


def calculate_hash(source, context):
    """Calculates checksum identifying translation."""
    if source is not None:
        data = source.encode() + context.encode()
    else:
        data = context.encode()
    # Need to convert it from unsigned 64-bit int to signed 64-bit int
    return siphash("Weblate Sip Hash", data) - 2 ** 63


def checksum_to_hash(checksum):
    """Converts hex to id_hash (signed 64-bit int)."""
    return int(checksum, 16) - 2 ** 63


def hash_to_checksum(id_hash):
    """Converts id_hash (signed 64-bit int) to unsigned hex."""
    return format(id_hash + 2 ** 63, "x")
