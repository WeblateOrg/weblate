# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Readiness tests, run inside the development Python environment."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from django.db import DatabaseError
from doctor import wait_for_services
from redis.exceptions import ConnectionError as RedisConnectionError


class ReadinessTests(unittest.TestCase):
    def test_database_startup_retry(self) -> None:
        cache = MagicMock()
        with (
            patch("doctor.connection") as database,
            patch("doctor.time.sleep") as sleep,
        ):
            database.cursor.side_effect = [DatabaseError("starting"), MagicMock()]
            wait_for_services(cache)
        database.close.assert_called_once()
        sleep.assert_called_once_with(1)
        cache.ping.assert_called_once()

    def test_valkey_timeout(self) -> None:
        cache = MagicMock()
        cache.ping.side_effect = RedisConnectionError("private diagnostic")
        with (
            patch("doctor.connection"),
            patch("doctor.time.monotonic", side_effect=[0, 61]),
            patch("doctor.time.sleep") as sleep,
            self.assertRaisesRegex(SystemExit, "unavailable after 60 seconds") as error,
        ):
            wait_for_services(cache)
        self.assertNotIn("private diagnostic", str(error.exception))
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
