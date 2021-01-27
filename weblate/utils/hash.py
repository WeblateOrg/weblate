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

from siphashc import siphash


def raw_hash(*parts: str):
    """Calculates checksum identifying translation."""
    data = "".join(part for part in parts)
    return siphash("Weblate Sip Hash", data)


def calculate_hash(*parts: str):
    """Calculates checksum identifying translation."""
    # Need to convert it from unsigned 64-bit int to signed 64-bit int
    return raw_hash(*parts) - 2 ** 63


def calculate_checksum(*parts: str):
    """Calcualtes siphashc checksum for given strings."""
    return format(raw_hash(*parts), "x")


def checksum_to_hash(checksum: str):
    """Converts hex to id_hash (signed 64-bit int)."""
    return int(checksum, 16) - 2 ** 63


def hash_to_checksum(id_hash: int):
    """Converts id_hash (signed 64-bit int) to unsigned hex."""
    return format(id_hash + 2 ** 63, "x")
