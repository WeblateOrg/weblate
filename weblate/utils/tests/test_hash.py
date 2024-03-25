# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase

from weblate.utils.hash import (
    calculate_checksum,
    calculate_dict_hash,
    calculate_hash,
    checksum_to_hash,
    hash_to_checksum,
)


class HashTest(SimpleTestCase):
    def test_hash(self) -> None:
        """Ensure hash is not changing."""
        text = "Message"
        text_hash = calculate_hash(text)
        self.assertEqual(text_hash, 8445691827737211251)
        self.assertEqual(text_hash, calculate_hash(text))

    def test_hash_context(self) -> None:
        """Ensure hash works with context."""
        text = "Message"
        context = "Context"
        text_hash = calculate_hash(context, text)
        self.assertEqual(text_hash, -1602104568316855346)
        self.assertEqual(text_hash, calculate_hash(context, text))

    def test_hash_unicode(self) -> None:
        """Ensure hash works for unicode."""
        text = "Příšerně žluťoučký kůň úpěl ďábelské ódy"
        text_hash = calculate_hash(text)
        self.assertEqual(text_hash, -4296353750398394478)
        self.assertEqual(text_hash, calculate_hash(text))

    def test_checksum(self) -> None:
        """Hash to checksum conversion."""
        text_hash = calculate_hash("Message")
        checksum = hash_to_checksum(text_hash)
        self.assertEqual(checksum, "f5351ff85ab23173")
        self.assertEqual(text_hash, checksum_to_hash(checksum))

    def test_calculate_checksum(self) -> None:
        self.assertEqual(calculate_checksum("Message"), "f5351ff85ab23173")

    def test_calculate_dict_hash(self) -> None:
        self.assertEqual(
            calculate_dict_hash({"a": 1, "b": 2}),
            calculate_dict_hash({"b": 2, "a": 1}),
        )
        self.assertEqual(
            calculate_dict_hash({"a": "1", "b": "2"}),
            calculate_dict_hash({"a": 1, "b": 2}),
        )
        self.assertNotEqual(
            calculate_dict_hash({"a": 2, "b": 2}),
            calculate_dict_hash({"a": 1, "b": 2}),
        )
