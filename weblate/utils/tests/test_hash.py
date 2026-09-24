# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from uuid import UUID

from django.test import SimpleTestCase

from weblate.utils.hash import (
    calculate_checksum,
    calculate_dict_hash,
    calculate_hash,
    calculate_json_fingerprint,
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

    def test_json_fingerprint_compatibility(self) -> None:
        """Stored dismissals and historical migrations need stable serialization."""
        self.assertEqual(
            calculate_json_fingerprint(
                {
                    "details": {"label": "Čeština", "count": 2},
                    "ids": [3, 1],
                    "revision": UUID("12345678-1234-5678-1234-567812345678"),
                }
            ),
            "4f210e9e14ee189de65e17fa4e261b87b122ba4eadbdc40bc31c9512202004cc",
        )

    def test_json_fingerprint_ordering(self) -> None:
        fingerprint = calculate_json_fingerprint(
            {"details": {"a": 1, "b": 2}, "ids": [3, 1]}
        )
        self.assertEqual(
            fingerprint,
            calculate_json_fingerprint({"ids": [3, 1], "details": {"b": 2, "a": 1}}),
        )
        self.assertNotEqual(
            fingerprint,
            calculate_json_fingerprint({"ids": [1, 3], "details": {"a": 1, "b": 2}}),
        )
        self.assertNotEqual(
            fingerprint,
            calculate_json_fingerprint({"ids": [3, 1], "details": {"a": 1, "b": "2"}}),
        )
