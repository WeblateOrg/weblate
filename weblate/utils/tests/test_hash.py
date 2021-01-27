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

from django.test import SimpleTestCase

from weblate.utils.hash import (
    calculate_checksum,
    calculate_hash,
    checksum_to_hash,
    hash_to_checksum,
)


class HashTest(SimpleTestCase):
    def test_hash(self):
        """Ensure hash is not changing."""
        text = "Message"
        text_hash = calculate_hash(text)
        self.assertEqual(text_hash, 8445691827737211251)
        self.assertEqual(text_hash, calculate_hash(text))

    def test_hash_context(self):
        """Ensure hash works with context."""
        text = "Message"
        context = "Context"
        text_hash = calculate_hash(context, text)
        self.assertEqual(text_hash, -1602104568316855346)
        self.assertEqual(text_hash, calculate_hash(context, text))

    def test_hash_unicode(self):
        """Ensure hash works for unicode."""
        text = "Příšerně žluťoučký kůň úpěl ďábelské ódy"
        text_hash = calculate_hash(text)
        self.assertEqual(text_hash, -4296353750398394478)
        self.assertEqual(text_hash, calculate_hash(text))

    def test_checksum(self):
        """Hash to checksum conversion."""
        text_hash = calculate_hash("Message")
        checksum = hash_to_checksum(text_hash)
        self.assertEqual(checksum, "f5351ff85ab23173")
        self.assertEqual(text_hash, checksum_to_hash(checksum))

    def test_calculate_checksum(self):
        self.assertEqual(calculate_checksum("Message"), "f5351ff85ab23173")
